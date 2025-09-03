from backend.gpt_engine import call_gpt

def generate_syllabus_prompt(data: dict) -> str:
    return call_gpt(f"""
Create a {data['duration']}-week syllabus on '{data['topic']}' for {data['audience']} learners.
Learning Outcomes: {data['outcomes']}
Preferred content: {', '.join(data['content_types'])}
References: {data.get('references') or 'None'}
Return structured week-wise topics only.
""")

def generate_detailed_content(syllabus_text: str) -> str:
    return call_gpt(f"""
Here is a course syllabus:\n\n{syllabus_text}

Generate detailed weekly content (headings + explanations + bullet points) for each week in this syllabus.
Include summaries and any quiz suggestions if relevant.
""")
