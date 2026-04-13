# generator.py

from gpt_engine import call_gpt
from typing import Dict, Any

def generate_syllabus_prompt(data: Dict[str, Any]) -> str:
    """
    data contains keys:
      - topic (str)
      - audience (str)
      - duration (str, "HH:MM")
      - content_types (Optional[str])
      - assessment_type (Optional[str])
      - attempts (Optional[int])
    """

    # human-friendly conversions
    duration = data.get("duration", "")
    content_types = data.get("content_types") or "Not specified"
    assessment_type = data.get("assessment_type")
    attempts = data.get("attempts")
    modules = data.get("modules")
    audience = data.get("audience")
    tone = data.get("ai_tone", "Formal")

    audience_rules = {
        "beginner": """
        - Assume NO prior knowledge
        - Start from fundamentals
        - Use simple and clear module titles
        - Include basic concepts and definitions
        - Avoid complex jargon
        """,
                "intermediate": """
        - Assume basic prior knowledge
        - Skip very basic introductions
        - Focus on practical usage and workflows
        - Include real-world applications
        - Use moderately technical terms
        """,
                "advanced": """
        - Assume strong prior knowledge
        - Focus on deep concepts and optimization
        - Include advanced topics and best practices
        - Use technical terminology
        - Avoid basic explanations
        """
            }

    assessment_line = ""
    if assessment_type:
        assessment_line = f" Assessment type: {assessment_type}."
        if attempts:
            assessment_line += f" Number of attempts allowed: {attempts}."

    prompt = f"""
Create a course syllabus for the topic '{data['topic']}' for {data['audience']} learners.
Audience Guidelines:{audience_rules.get(audience, audience_rules["beginner"])}
Total duration: {duration} (hours:minutes).
Number of modules required: {modules}.
Preferred content types: {content_types}.{assessment_line}
Write the syllabus in a {tone.lower()} tone.
{assessment_line}

Return structured module-wise syllabus:
- Each module must have a title
- Modules should have short description
- Module titles MUST reflect audience level
    - Beginner → simple names
    - Intermediate → practical names
    - Advanced → technical names
- Keep structure clean and consistent
- Do NOT use markdown symbols (#, *, etc.)
- Use plain text only
"""

    # Trim and pass to GPT engine
    return call_gpt(prompt.strip())
