import tempfile
import uuid
from dotenv import load_dotenv

from gpt_engine import call_gpt

load_dotenv()

from fastapi import Body, FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from models import SyllabusRequest, UpdateContentRequest

from generator import generate_syllabus_prompt
from sqlalchemy import Column, String, Date
from sqlalchemy.ext.declarative import declarative_base
from chatbot_logic import get_report_categories, get_courses_by_status, handle_selection
from career_path import (
    CareerPathRequest,
    CareerPathResponse,
    generate_career_path_logic,
)

from datetime import datetime
import urllib.parse
import json
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from auth.identity import GetCurrentUser
from auth.swagger_oauth import (
    get_swagger_ui_parameters,
    get_oauth2_scheme_config,
    ENABLE_SWAGGER_OAUTH,
)

from scorm_exporter import generate_scorm
from azure_blob_utils import (
    upload_file_to_blob,
    list_all_scorm_files,
    list_blobs_in_container,
    search_scorm_files,
    filter_scorm_files,
    blob_service_client,
    AZURE_BLOB_CONTAINER,
    get_blob_sas_url,
)
import os
import zipfile
from pydantic import BaseModel
from fastapi import Query
import shutil

app = FastAPI(
    title="LMS Course Generation API",
    description="AI-powered course generation with Identity Server authentication",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

GENERATED_DIR = "generated_syllabus"
VERIFIED_DIR = "verified_syllabus"
DETAILED_DIR = "detailed_courses"
FINAL_DIR = "final_courses"
os.makedirs(GENERATED_DIR, exist_ok=True)
os.makedirs(DETAILED_DIR, exist_ok=True)
os.makedirs(FINAL_DIR, exist_ok=True)

# ============================================================
# IDENTITY SERVER TEST ENDPOINTS
# ============================================================


@app.get("/test/auth-status")
async def test_auth_status():
    """Check authentication configuration - PUBLIC endpoint"""
    from auth.identity import AUTHENTICATION, IDENTITY_SERVER_AUTHENTICATION

    return {
        "status": "ok",
        "authentication_enabled": AUTHENTICATION,
        "identity_server_enabled": IDENTITY_SERVER_AUTHENTICATION,
        "identity_server_url": os.getenv("IDENTITY_SERVER_ISSUER"),
        "message": "Backend running. Test with /test/protected",
    }


@app.get("/test/protected")
async def test_protected_endpoint(current_user: dict = Depends(GetCurrentUser)):
    """PROTECTED - Requires valid token from Identity Server"""
    return {
        "status": "authenticated",
        "message": "🎉 SUCCESS! Identity Server validated your token!",
        "user_id": current_user.get("user_id"),
        "scopes": current_user.get("scopes"),
        "proof": "This response means: FastAPI → Identity Server → Validated → Success",
    }


@app.post("/test/get-token")
async def test_get_service_token():
    """Get service token from Identity Server"""
    from auth.identity import GetToken

    try:
        token = await GetToken()
        return {
            "success": True,
            "token_preview": f"{token}",
            "next": "Use: curl -H 'Authorization: Bearer TOKEN' http://127.0.0.1:8000/test/protected",
        }
    except Exception as e:
        return {"error": str(e)}


# ============================================================
app.mount("/scorm_final", StaticFiles(directory=FINAL_DIR), name="scorm_final")

# Serve SCORM
app.mount("/scorm", StaticFiles(directory=DETAILED_DIR), name="scorm")


@app.post("/generate_syllabus/")
def generate_syllabus(
    request: SyllabusRequest, current_user: dict = Depends(GetCurrentUser)):
    syllabus = generate_syllabus_prompt(request.dict())
    syllabus_id = str(uuid.uuid4())
    name = f"{request.topic.replace(' ', '_').lower()}_{request.audience.lower()}_{syllabus_id[:8]}"
    folder = os.path.join(GENERATED_DIR, name)
    os.makedirs(folder, exist_ok=True)

    # write syllabus
    with open(os.path.join(folder, "syllabus.txt"), "w", encoding="utf-8") as f:
        f.write(syllabus)

    # save metadata so later steps (generate content -> scorm) can access assessment info
    meta = {
        "syllabus_id": syllabus_id,
        "topic": request.topic,
        "audience": request.audience,
        "duration": request.duration,
        "content_types": request.content_types,
        "assessment_type": getattr(request, "assessment_type", None),
        "attempts": getattr(request, "attempts", None),
        "modules": getattr(request, "modules", None),
        "ai_tone": getattr(request, "ai_tone", None),
    }
    with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as m:
        json.dump(meta, m)

    return {"syllabus_name": name, "syllabus": syllabus}


@app.get("/generated_syllabus/")
def get_generated_syllabus(current_user: dict = Depends(GetCurrentUser)):
    items = []
    for name in os.listdir(GENERATED_DIR):
        path = os.path.join(GENERATED_DIR, name, "syllabus.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                items.append({"syllabus_name": name, "syllabus": f.read()})
    return items

@app.post("/generate_content_from_syllabus/{syllabus_name}")
def generate_detailed_content_from_syllabus(syllabus_name: str, current_user: dict = Depends(GetCurrentUser)):

    syllabus_path = os.path.join(GENERATED_DIR, syllabus_name, "syllabus.txt")  
    meta_path = os.path.join(GENERATED_DIR, syllabus_name, "meta.json")
    course_id = str(uuid.uuid4())
    meta = {}   # meta initialization

    if not os.path.exists(syllabus_path):
        raise HTTPException(status_code=404, detail="Syllabus not found.")

    # Read syllabus
    with open(syllabus_path, "r", encoding="utf-8") as f:
        syllabus = f.read()

    # Read meta (tone + assessment config)
    ai_tone = "Formal"
    assessment_type = None
    attempts = None

    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as m:
                meta = json.load(m)
                ai_tone = meta.get("ai_tone", "Formal")
                assessment_type = meta.get("assessment_type")
                attempts = meta.get("attempts")
        except Exception:
            pass
    # Attach course_id AFTER meta is loaded
    meta["course_id"] = course_id

    # STEP 1: Extract modules from syllabus
    import re
    module_titles = re.findall(r"Module\s+\d+:\s*(.*)", syllabus)

    if not module_titles:
        raise HTTPException(status_code=400, detail="No modules found in syllabus.")

    # STEP 2: Generate content module-by-module (KEY FIX)
    detailed_content = ""
    separator = "\n\n--------------------------------------------\n\n"

    for idx, module_title in enumerate(module_titles, start=1):
        print(f"[INFO] Generating Module {idx}: {module_title}")

        module_content = call_gpt(f"""
You are an expert instructional designer.

Generate detailed content ONLY for this module:

Module: {module_title}

STRUCTURE:

1. Introduction:
(150–200 words)

2. Explanation:
(300–500 words)

3. Subtopics:
- Minimum 5 and maximum 6 subtopics

4. Subtopic Explanation:

For EACH subtopic include:
- Explanation (100–150 words)
- Syntax (if applicable)
- Example (code or real-world)

STRICT RULES:
- Do NOT generate other modules
- Do NOT stop early
- Do NOT use markdown (#, *, etc.)
- Use plain text only
- Keep it beginner-friendly and practical

Tone: {ai_tone}
""".strip())

        detailed_content += f"{separator}Module {idx}: {module_title}\n\n"
        detailed_content += module_content.strip()

    # STEP 3: Save locally (outline.txt)
    folder = os.path.join(DETAILED_DIR, syllabus_name)
    os.makedirs(folder, exist_ok=True)

    outline_path = os.path.join(folder, "outline.txt")

    with open(outline_path, "w", encoding="utf-8") as f:
        f.write(detailed_content)

    # STEP 4: Upload outline to Azure
    upload_file_to_blob(
        outline_path,
        f"{syllabus_name}/outline.txt"
    )

    # STEP 5: Upload meta.json
    with open(meta_path, "w", encoding="utf-8") as m:
        json.dump(meta, m)

    # Upload updated meta
    upload_file_to_blob(
        meta_path,
        f"{syllabus_name}/meta.json"
    )

    # STEP 6: Generate SCORM
    zip_path = generate_scorm(
        detailed_content,
        output_dir=folder,
        assessment_type=assessment_type,
        attempts=attempts,
        course_id=course_id
    )

    # STEP 7: Upload SCORM
    blob_name = f"{syllabus_name}.zip"
    scorm_url = upload_file_to_blob(zip_path, blob_name)

    # FINAL RESPONSE
    return {
        "course_name": syllabus_name,
        "outline": detailed_content,
        "scorm_url": scorm_url,
        "editable": True
    }

def upload_text_to_blob(blob_name: str, content: str):
    blob_client = blob_service_client.get_blob_client(
        container=AZURE_BLOB_CONTAINER,
        blob=blob_name
    )
    blob_client.upload_blob(content, overwrite=True)


def download_blob_as_text(blob_name: str) -> str:
    blob_client = blob_service_client.get_blob_client(
        container=AZURE_BLOB_CONTAINER,
        blob=blob_name
    )
    return blob_client.download_blob().readall().decode("utf-8")

@app.post("/update_detailed_content/{syllabus_name}")
def update_detailed_content(
    syllabus_name: str,
    updated_content: str = Body(..., media_type="text/plain"), current_user: dict = Depends(GetCurrentUser)
):

    assessment_type = None
    attempts = None
    try:
        meta_content = download_blob_as_text(f"{syllabus_name}/meta.json")
        meta = json.loads(meta_content)
        assessment_type = meta.get("assessment_type")
        attempts = meta.get("attempts")
    except:
        pass

    # Generate NEW course_id for this version
    course_id = str(uuid.uuid4())

    # Generate SCORM in temp folder
    with tempfile.TemporaryDirectory() as tmp_dir:

        outline_path = os.path.join(tmp_dir, "outline.txt")
        with open(outline_path, "w", encoding="utf-8") as f:
            f.write(updated_content)

        zip_path = generate_scorm(
            updated_content,
            output_dir=tmp_dir,
            assessment_type=assessment_type,
            attempts=attempts,
            course_id=course_id
        )

        # Generate timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")

        # Create versioned name
        versioned_name = f"{syllabus_name}_updated_{timestamp}.zip"

        scorm_url = upload_file_to_blob(
            zip_path,
            f"{syllabus_name}/{versioned_name}"
        )

        # Overwrite outline in Azure directly
        upload_text_to_blob(
            blob_name=f"{syllabus_name}/outline.txt",
            content=updated_content
        )

         # Update meta.json with version tracking
        meta.setdefault("versions", [])

        meta["versions"].append({
            "course_id": course_id,
            "updated_at": timestamp,
            "scorm_file": versioned_name
        })

        meta["latest_course_id"] = course_id

        # save back
        upload_text_to_blob(
            blob_name=f"{syllabus_name}/meta.json",
            content=json.dumps(meta)
        )

    return {
        "message": "Content updated successfully",
        "course_id": course_id,
        "scorm_url": scorm_url
    }

@app.get("/final_courses/")
def list_final_courses(current_user: dict = Depends(GetCurrentUser)):
    files = list_all_scorm_files()
    return [
        {
            "course_name": os.path.splitext(os.path.basename(f))[0],
            "scorm_url": f"https://{blob_service_client.account_name}.blob.core.windows.net/{AZURE_BLOB_CONTAINER}/{f}",
        }
        for f in files
    ]


@app.get("/final_courses/search")
def search_final_courses(
    query: str = Query(...), current_user: dict = Depends(GetCurrentUser)
):
    files = search_scorm_files(query)
    results = []
    for f in files:
        course_name = os.path.splitext(os.path.basename(f))[0]
        scorm_url = get_blob_sas_url(f)  # Same format as upload_file_to_blob
        results.append({"course_name": course_name, "scorm_url": scorm_url})
    return results


@app.get("/final_courses/filter")
def filter_final_courses(
    filter: str = Query(...), current_user: dict = Depends(GetCurrentUser)
):
    files = filter_scorm_files(filter)
    results = []
    for f in files:
        course_name = os.path.splitext(os.path.basename(f))[0]
        scorm_url = get_blob_sas_url(f)  # Same format as upload_file_to_blob
        results.append({"course_name": course_name, "scorm_url": scorm_url})
    return results


# ============================================================
#  REPORT GENERATOR ENDPOINTS (from chatbot_ui)
# ============================================================


class SelectionRequest(BaseModel):
    course: str = ""
    learner: str = ""
    status: str = ""


@app.get("/course-reports")
def get_reports(current_user: dict = Depends(GetCurrentUser)):
    """Step 1: Return static report categories"""
    return {"categories": get_report_categories()}


@app.get("/course-reports/{status}")
def get_courses(status: str, current_user: dict = Depends(GetCurrentUser)):
    """Step 2: Return distinct courses by status"""
    return get_courses_by_status(status)


@app.post("/course-reports/select")
def select_item(req: SelectionRequest, current_user: dict = Depends(GetCurrentUser)):
    """Step 3: Select course or learner with optional status"""
    return handle_selection(req.course, req.learner, req.status)


# ============================================================
# Health Check
# ============================================================
@app.get("/")
def root():
    return {"message": "LMS Unified API running successfully!"}


#####Career path endpoint
@app.post("/career-path/", response_model=CareerPathResponse)
def generate_career_path(
    request: CareerPathRequest, current_user: dict = Depends(GetCurrentUser)
):
    """
    Generate career path courses based on user input (Business Analyst → Program Manager, etc.)
    """
    try:
        response = generate_career_path_logic(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
