from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from models import SyllabusRequest
from generator import generate_syllabus_prompt, generate_detailed_content
from scorm_exporter import generate_scorm
import os
import zipfile
from pydantic import BaseModel
from fastapi import Query

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
os.makedirs(VERIFIED_DIR, exist_ok=True)
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


@app.post("/verify_syllabus/{syllabus_name}")
def verify_syllabus(syllabus_name: str):
    src = os.path.join(GENERATED_DIR, syllabus_name, "syllabus.txt")
    dst = os.path.join(VERIFIED_DIR, syllabus_name)
    os.makedirs(dst, exist_ok=True)

    if not os.path.exists(src):
        raise HTTPException(status_code=404, detail="Syllabus not found.")

    with open(src, "r", encoding="utf-8") as f:
        content = f.read()
    with open(os.path.join(dst, "syllabus.txt"), "w", encoding="utf-8") as f:
        f.write(content)

    return {"message": f"Syllabus '{syllabus_name}' verified."}


@app.post("/generate_content_from_syllabus/{syllabus_name}")
def generate_detailed_content_from_syllabus(syllabus_name: str):
    syllabus_path = os.path.join(VERIFIED_DIR, syllabus_name, "syllabus.txt")
    if not os.path.exists(syllabus_path):
        raise HTTPException(status_code=404, detail="Syllabus not verified.")

    with open(syllabus_path, "r", encoding="utf-8") as f:
        syllabus = f.read()

    detailed_content = generate_detailed_content(syllabus)
    folder = os.path.join(DETAILED_DIR, syllabus_name)
    os.makedirs(folder, exist_ok=True)

    with open(os.path.join(folder, "outline.txt"), "w", encoding="utf-8") as f:
        f.write(detailed_content)

    generate_scorm(detailed_content, output_dir=folder)

    return {
        "course_name": syllabus_name,
        "outline": detailed_content,
        "scorm_url": f"http://localhost:8000/scorm/{syllabus_name}/index.html"
    }

class EditedSyllabus(BaseModel):
    syllabus_name: str
    syllabus_text: str

@app.post("/save_edited_syllabus/")
def save_edited_syllabus(data: EditedSyllabus):
    name = data.syllabus_name
    text = data.syllabus_text

    folder = os.path.join(GENERATED_DIR, name)
    os.makedirs(folder, exist_ok=True)

    syllabus_path = os.path.join(folder, "syllabus.txt")
    with open(syllabus_path, "w", encoding="utf-8") as f:
        f.write(text)

    return {"message": "Edited syllabus saved successfully"}

@app.get("/final_courses/")
def list_final_courses():
    final_list = []
    source_dir = DETAILED_DIR  # ✅ Read from detailed_courses

    for course_name in sorted(os.listdir(source_dir), reverse=True):
        course_path = os.path.join(source_dir, course_name)
        outline_path = os.path.join(course_path, "outline.txt")
        scorm_index = os.path.join(course_path, "index.html")

        if os.path.exists(outline_path) and os.path.exists(scorm_index):
            with open(outline_path, "r", encoding="utf-8") as f:
                outline = f.read()

            final_list.append({
                "course_name": course_name,
                "outline": outline,
                "scorm_url": f"http://localhost:8000/scorm/{course_name}/index.html"  # ✅ uses detailed path
            })

    return final_list


@app.get("/final_courses/search")
def search_final_courses(query: str = Query(...)):
    """
    Search final courses by keyword in course_name or outline content.
    """
    results = []
    for course_name in os.listdir(DETAILED_DIR):  # Reads from detailed_courses
        course_path = os.path.join(DETAILED_DIR, course_name)
        outline_path = os.path.join(course_path, "outline.txt")
        if os.path.exists(outline_path):
            with open(outline_path, "r", encoding="utf-8") as f:
                content = f.read()
            if query.lower() in course_name.lower() or query.lower() in content.lower():
                results.append({
                    "course_name": course_name,
                    "outline": content,
                    "scorm_url": f"http://localhost:8000/scorm/{course_name}/index.html"
                })
    return results


@app.get("/final_courses/filter")
def filter_final_courses(filter: str = Query(...)):
    """
    Filter final courses by substring match in course_name only.
    """
    results = []
    for course_name in os.listdir(DETAILED_DIR):  # Reads from detailed_courses
        if filter.lower() in course_name.lower():
            course_path = os.path.join(DETAILED_DIR, course_name)
            outline_path = os.path.join(course_path, "outline.txt")
            if os.path.exists(outline_path):
                with open(outline_path, "r", encoding="utf-8") as f:
                    content = f.read()
                results.append({
                    "course_name": course_name,
                    "outline": content,
                    "scorm_url": f"http://localhost:8000/scorm/{course_name}/index.html"
                })
    return results
