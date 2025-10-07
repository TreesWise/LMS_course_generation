from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from models import SyllabusRequest
from generator import generate_syllabus_prompt, generate_detailed_content
from sqlalchemy import Column, String, Date
from sqlalchemy.ext.declarative import declarative_base
from chatbot_logic import (
    get_report_categories,
    get_courses_by_status,
    handle_selection
)
 
import urllib.parse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
 
 
 
 
from scorm_exporter import generate_scorm
from azure_blob_utils import (
    upload_file_to_blob,
    list_all_scorm_files,
    list_blobs_in_container,
    search_scorm_files,
    filter_scorm_files,
    blob_service_client,
    AZURE_BLOB_CONTAINER,
    get_blob_sas_url
)
import os
import zipfile
from pydantic import BaseModel
from fastapi import Query
import shutil
app = FastAPI()
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)
 
GENERATED_DIR = "generated_syllabus"
VERIFIED_DIR = "verified_syllabus"
DETAILED_DIR = "detailed_courses"
FINAL_DIR = "final_courses"
os.makedirs(GENERATED_DIR, exist_ok=True)
os.makedirs(DETAILED_DIR, exist_ok=True)
os.makedirs(FINAL_DIR, exist_ok=True)
 
app.mount("/scorm_final", StaticFiles(directory=FINAL_DIR), name="scorm_final")
 
# Serve SCORM
app.mount("/scorm", StaticFiles(directory=DETAILED_DIR), name="scorm")
 
 
@app.post("/generate_syllabus/")
def generate_syllabus(request: SyllabusRequest):
    syllabus = generate_syllabus_prompt(request.dict())
    name = f"{request.topic.replace(' ', '_').lower()}_{request.audience.lower()}"
    folder = os.path.join(GENERATED_DIR, name)
    os.makedirs(folder, exist_ok=True)
 
    with open(os.path.join(folder, "syllabus.txt"), "w", encoding="utf-8") as f:
        f.write(syllabus)
 
    return {"syllabus_name": name, "syllabus": syllabus}
 
 
@app.get("/generated_syllabus/")
def get_generated_syllabus():
    items = []
    for name in os.listdir(GENERATED_DIR):
        path = os.path.join(GENERATED_DIR, name, "syllabus.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                items.append({"syllabus_name": name, "syllabus": f.read()})
    return items
 
 
@app.post("/generate_content_from_syllabus/{syllabus_name}")
def generate_detailed_content_from_syllabus(syllabus_name: str):
    syllabus_path = os.path.join(GENERATED_DIR, syllabus_name, "syllabus.txt")
    if not os.path.exists(syllabus_path):
        raise HTTPException(status_code=404, detail="Syllabus not verified.")
 
    with open(syllabus_path, "r", encoding="utf-8") as f:
        syllabus = f.read()
 
    detailed_content = generate_detailed_content(syllabus)
 
    # Local temp folder
    folder = os.path.join(DETAILED_DIR, syllabus_name)
    os.makedirs(folder, exist_ok=True)
 
    with open(os.path.join(folder, "outline.txt"), "w", encoding="utf-8") as f:
        f.write(detailed_content)
 
    # Generate SCORM locally
    zip_path = generate_scorm(detailed_content, output_dir=folder)
 
    # Upload zip to Azure Blob
    blob_name = f"{syllabus_name}.zip"
    scorm_url = upload_file_to_blob(zip_path, blob_name);
   
    list_blobs_in_container()
 
    # Cleanup local files (optional, keeps disk clean)
    try:
        shutil.rmtree(folder)
        os.remove(zip_path)
    except Exception:
        pass
 
    return {
        "course_name": syllabus_name,
        "outline": detailed_content,
        "scorm_url": scorm_url   # ✅ Now returns SAS URL from Azure
    }
 
 
@app.get("/final_courses/")
def list_final_courses():
    files = list_all_scorm_files()
    return [
        {
            "course_name": os.path.splitext(os.path.basename(f))[0],
            "scorm_url": f"https://{blob_service_client.account_name}.blob.core.windows.net/{AZURE_BLOB_CONTAINER}/{f}"
        }
        for f in files
    ]
 
 
@app.get("/final_courses/search")
def search_final_courses(query: str = Query(...)):
    files = search_scorm_files(query)
    results = []
    for f in files:
        course_name = os.path.splitext(os.path.basename(f))[0]
        scorm_url = get_blob_sas_url(f)  # ✅ Same format as upload_file_to_blob
        results.append({
            "course_name": course_name,
            "scorm_url": scorm_url
        })
    return results
 
 
@app.get("/final_courses/filter")
def filter_final_courses(filter: str = Query(...)):
    files = filter_scorm_files(filter)
    results = []
    for f in files:
        course_name = os.path.splitext(os.path.basename(f))[0]
        scorm_url = get_blob_sas_url(f)  # ✅ Same format as upload_file_to_blob
        results.append({
            "course_name": course_name,
            "scorm_url": scorm_url
        })
    return results
 
 
 
# ============================================================
#  REPORT GENERATOR ENDPOINTS (from chatbot_ui)
# ============================================================
 
class SelectionRequest(BaseModel):
    course: str = ""
    learner: str = ""
    status: str = ""
 
 
@app.get("/course-reports")
def get_reports():
    """Step 1: Return static report categories"""
    return {"categories": get_report_categories()}
 
 
@app.get("/course-reports/{status}")
def get_courses(status: str):
    """Step 2: Return distinct courses by status"""
    return get_courses_by_status(status)
 
 
@app.post("/course-reports/select")
def select_item(req: SelectionRequest):
    """Step 3: Select course or learner with optional status"""
    return handle_selection(req.course, req.learner, req.status)
 
 
# ============================================================
# Health Check
# ============================================================
@app.get("/")
def root():
    return {"message": "✅ LMS Unified API running successfully!"}
