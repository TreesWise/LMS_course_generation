from fastapi import FastAPI
from pydantic import BaseModel
from report_generator.chatbot_logic import get_report_categories, get_courses_by_status, handle_selection
 
app = FastAPI(title="LMS Course Reports API")
 
# --------------------------
# Pydantic Models
# --------------------------
class SelectionRequest(BaseModel):
    course: str = ""
    learner: str = ""
    status: str = ""   # ✅ include status to filter properly
 
 
# --------------------------
# Endpoints
# --------------------------
 
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