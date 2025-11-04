from pydantic import BaseModel
from typing import List, Optional

class SyllabusRequest(BaseModel):
    topic: str
    audience: str
    duration: int
    outcomes: str
    content_types: List[str]
    references: Optional[str] = None
