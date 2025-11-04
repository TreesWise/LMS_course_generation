
from pydantic import BaseModel
from typing import List
from openai import AzureOpenAI
from dotenv import load_dotenv
import os
import json
 
# Load env vars
load_dotenv()
 
## Azure OpenAI credentials
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
 
# Initialize Azure OpenAI client
client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)
 
# Input schema
class CareerPathRequest(BaseModel):
    current_role: str
    target_role: str
    course_start_date: str
    course_end_date: str
    estimated_weekly_hours: int
 
# Output schema
class Course(BaseModel):
    course_name: str
    description: str
    category: str
    level: str
    estimated_hours: int
    mandatory: bool
    thumbnail_url: str
 
class CareerPathResponse(BaseModel):
    courses: List[Course]
 
 
def generate_career_path_logic(request: CareerPathRequest) -> CareerPathResponse:
    """
    Generate a simplified career path course list using GPT-4o.
    """
 
    system_prompt = """You are an AI career path advisor.
    Based on the given current role, target role, start/end dates,
    and weekly hours, suggest a list of courses.
 
    Rules:
    - Output must be strictly valid JSON (no markdown, no text).
    - Only return a "courses" array.
    - Each course object must include:
      course_name, description, category, level, estimated_hours, mandatory, thumbnail_url
    - The "mandatory" field must be true if the learner cannot skip this course, otherwise false.
    - "thumbnail_url" must be relevant to course name.
    - "thumbnail_url" must be a valid, working public image URL (prefer from Unsplash, Pexels, or Pixabay)
      and relevant to the course topic (e.g., use https://www.google.com/search?tbm=isch&q=<keywords>).
    - Keep the list concise (4–6 courses max).
    """
 
    user_prompt = f"""
    Current role: {request.current_role}
    Target role: {request.target_role}
    Course start date: {request.course_start_date}
    Course end date: {request.course_end_date}
    Estimated weekly hours: {request.estimated_weekly_hours}
    """
 
    response = client.chat.completions.create(
        model=AZURE_OPENAI_DEPLOYMENT_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=600,
        response_format={"type": "json_object"}  # ✅ Force JSON
    )
 
    content = response.choices[0].message.content
    data = json.loads(content)
    return CareerPathResponse(**data)