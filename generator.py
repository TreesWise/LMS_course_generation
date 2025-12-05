# from gpt_engine import call_gpt

# def generate_syllabus_prompt(data: dict) -> str:
#     return call_gpt(f"""
# Create a {data['duration']}-week syllabus on '{data['topic']}' for {data['audience']} learners.
# Learning Outcomes: {data['outcomes']}
# Preferred content: {', '.join(data['content_types'])}
# References: {data.get('references') or 'None'}
# Return structured week-wise topics only.
# """)

# def generate_detailed_content(syllabus_text: str) -> str:
#     return call_gpt(f"""
# Here is a course syllabus:\n\n{syllabus_text}

# Generate detailed weekly content (headings + explanations + bullet points) for each week in this syllabus.
# Include summaries and any quiz suggestions if relevant.
# """)





# from gpt_engine import call_gpt

# def generate_syllabus_prompt(data: dict) -> str:
#     return call_gpt(f"""
# Create a {data['duration']}-week syllabus on '{data['topic']}' for {data['audience']} learners.
# Learning Outcomes: {data['outcomes']}
# Preferred content: {', '.join(data['content_types'])}
# References: {data.get('references') or 'None'}
# Return structured week-wise topics only.
# """)

# def generate_detailed_content(syllabus_text: str) -> str:
#     return call_gpt(f"""
# Here is a course syllabus:\n\n{syllabus_text}

# Generate detailed weekly content (headings + explanations + bullet points) for each week in this syllabus.
# Include summaries and any quiz suggestions if relevant.
# """)



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
    tone = data.get("ai_tone", "Formal")

    assessment_line = ""
    if assessment_type:
        assessment_line = f" Assessment type: {assessment_type}."
        if attempts:
            assessment_line += f" Number of attempts allowed: {attempts}."

    prompt = f"""
Create a course syllabus for the topic '{data['topic']}' for {data['audience']} learners.
Total duration: {duration} (hours:minutes).
Number of modules required: {modules}.
Preferred content types: {content_types}.{assessment_line}
Write the syllabus in a {tone.lower()} tone.
{assessment_line}

Return structured module-wise syllabus:
- Each module must have a title
- Modules should have short description"""

    # Trim and pass to GPT engine
    return call_gpt(prompt.strip())


def generate_detailed_content(syllabus_text: str, ai_tone: str = "Formal") -> str:
    return call_gpt(f"""
Here is a course syllabus:\n\n{syllabus_text}

Generate detailed module content in a {ai_tone.lower()} tone.
Each module should contain:
- Clear explanation
- Bullet points
- Example scenarios
- Summary at module end
""".strip())
