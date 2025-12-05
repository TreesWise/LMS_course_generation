# from pydantic import BaseModel
# from typing import List, Optional

# class SyllabusRequest(BaseModel):
#     topic: str
#     audience: str
#     duration: int
#     outcomes: str
#     content_types: List[str]
#     references: Optional[str] = None


from pydantic import BaseModel, field_validator
from typing import List, Optional
import re

class SyllabusRequest(BaseModel):
    topic: str
    audience: str
    duration: str                # Format "HH:MM" where HH = 0..52, MM = 00..59
    content_types: Optional[str] = None   # previously list -> now string or null
    assessment_type: Optional[str] = None  # "MCQ" or "True/False"
    attempts: Optional[int] = None         # 1, 2 or 3
    modules: int                 # number of modules in course

    @field_validator("duration")
    def validate_duration(cls, v: str):
        # Accept formats like "04:30" or "4:30"
        if not isinstance(v, str):
            raise ValueError("duration must be a string in format HH:MM")
        m = re.match(r"^(\d{1,2}):([0-5][0-9])$", v.strip())
        if not m:
            raise ValueError("duration must be in format HH:MM with minutes 00-59")
        hours = int(m.group(1))
        if hours < 0 or hours > 52:
            raise ValueError("duration hours must be between 0 and 52")
        return v.strip()

    @field_validator("assessment_type")
    def validate_assessment_type(cls, v):
        if v is None:
            return v
        allowed = {"MCQ", "True/False"}
        if v not in allowed:
            raise ValueError(f"assessment_type must be one of {sorted(allowed)}")
        return v

    @field_validator("attempts")
    def validate_attempts(cls, v):
        if v is None:
            return v
        if v not in (1, 2, 3):
            raise ValueError("attempts must be one of 1, 2, or 3")
        return v

    @field_validator("modules")
    def validate_modules(cls, v):
        if v < 1:
            raise ValueError("modules must be >= 1")
        return v
