# import os
# import zipfile

# def generate_scorm(course_text: str, output_dir: str = "scorm_package") -> str:
#     os.makedirs(output_dir, exist_ok=True)

#     # Save index.html
#     with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
#         f.write(f"<html><body><pre>{course_text}</pre></body></html>")

#     # Save imsmanifest.xml
#     manifest = """<?xml version="1.0" encoding="UTF-8"?>
# <manifest identifier="com.example.ai-course"
#     version="1.0"
#     xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
#     xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3"
#     xmlns:imsss="http://www.imsglobal.org/xsd/imsss"
#     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
#     xsi:schemaLocation="
#       http://www.imsglobal.org/xsd/imscp_v1p1                 imscp_v1p1.xsd
#       http://www.adlnet.org/xsd/adlcp_v1p3                    adlcp_v1p3.xsd
#       http://www.imsglobal.org/xsd/imsss                      imsss_v1p0.xsd">

#   <organizations default="org1">
#     <organization identifier="org1">
#       <title>AI Generated Course</title>
#       <item identifier="item1" identifierref="resource1" isvisible="true">
#         <title>Lesson 1</title>
#         <imsss:sequencing>
#           <imsss:controlMode flow="true" completionSetByContent="true"/>
#           <imsss:objectives>
#             <imsss:primaryObjective objectiveID="completion">
#               <imsss:minNormalizedMeasure>0.8</imsss:minNormalizedMeasure>
#             </imsss:primaryObjective>
#           </imsss:objectives>
#         </imsss:sequencing>
#       </item>
#     </organization>
#   </organizations>

#   <resources>
#     <resource identifier="resource1" type="webcontent" adlcp:scormType="sco" href="index.html">
#       <file href="index.html"/>
#       <adlcp:completionThreshold>0.8</adlcp:completionThreshold>
#     </resource>
#   </resources>
# </manifest>"""

#     with open(os.path.join(output_dir, "imsmanifest.xml"), "w", encoding="utf-8") as f:
#         f.write(manifest)

#     # ✅ FIX: Save .zip INSIDE the course folder with correct name
#     zip_name = f"{os.path.basename(output_dir)}.zip"
#     zip_path = os.path.join(output_dir, zip_name)

#     with zipfile.ZipFile(zip_path, 'w') as zipf:
#         for root, _, files in os.walk(output_dir):
#             for file in files:
#                 full_path = os.path.join(root, file)
#                 arcname = os.path.relpath(full_path, output_dir)
#                 if file != zip_name:
#                     zipf.write(full_path, arcname=arcname)

#     return zip_path




# scorm_exporter.py
import os
import zipfile
import html
import json
from typing import Optional

# Try to import your project's GPT wrapper. If missing, fallback to None.
try:
    from gpt_engine import call_gpt
except Exception:
    call_gpt = None


def _ask_gpt_for_questions(course_text: str, assessment_type: str) -> Optional[list]:
    """
    Ask the GPT engine to generate 5 contextual questions based on course_text.
    Expected JSON structure from GPT:
    [
      {
        "q":"Question text",
        "type":"mcq"|"tf",
        "options":["opt1","opt2","opt3","opt4"]  # for mcq
        "answer_index": 0  # index in options for mcq
        OR
        "answer": "True"|"False"   # for tf
      },
      ...
    ]
    Returns list of question dicts, or None on error.
    """
    if call_gpt is None:
        return None

    system_prompt = (
        "You are a helpful assistant that creates short assessment questions "
        "from a course text. Return ONLY a JSON array (no explanation). "
        "Create exactly 5 questions.\n\n"
        "Each question item must be an object with these fields:\n"
        "- q: question text (string)\n"
        "- type: 'mcq' or 'tf'\n"
        "- options: array of strings (only for mcq, 4 items)\n"
        "- answer_index: integer (0-based index into options) for mcq\n"
        "- answer: 'True' or 'False' for tf\n\n"
        "Make questions based on the course content provided. Keep options concise."
    )

    prompt = f"{system_prompt}\n\nCourse text:\n{course_text[:4000]}"  # limit length

    try:
        raw = call_gpt(prompt)
        txt = raw.strip()
        # remove ```json or ``` wrappers if present
        if txt.startswith("```"):
            parts = txt.split("```")
            candidate = max(parts, key=len)
            txt = candidate.strip()
        # find JSON array
        start = txt.find("[")
        end = txt.rfind("]")
        if start != -1 and end != -1:
            txt = txt[start:end+1]
        questions = json.loads(txt)
        if not isinstance(questions, list) or len(questions) != 5:
            return None
        validated = []
        for q in questions:
            if not isinstance(q, dict):
                return None
            qtype = q.get("type", "").lower()
            if qtype == "mcq":
                opts = q.get("options")
                idx = q.get("answer_index")
                if not isinstance(opts, list) or len(opts) < 2 or not isinstance(idx, int):
                    return None
                validated.append({
                    "q": str(q.get("q", "")),
                    "type": "mcq",
                    "options": [str(o) for o in opts],
                    "answer_index": int(idx)
                })
            elif qtype in ("tf", "truefalse", "true_false", "tf"):
                ans = q.get("answer", "")
                ans_norm = "True" if str(ans).strip().lower().startswith("t") else "False"
                validated.append({
                    "q": str(q.get("q", "")),
                    "type": "tf",
                    "answer": ans_norm
                })
            else:
                return None
        return validated
    except Exception:
        return None


def _fallback_questions(course_title: str, assessment_type: str) -> list:
    """
    Return 5 simple fallback questions (deterministic).
    For MCQ each question has 4 options with option 0 being correct.
    For TF the correct answer is True for all.
    """
    q_texts = [
        f"What is a core idea in {course_title}?",
        f"Which statement about {course_title} is correct?",
        f"How would {course_title} be applied?",
        f"Which topic is usually covered in {course_title}?",
        f"A common tool related to {course_title} is?"
    ]
    questions = []
    for q in q_texts:
        if assessment_type and assessment_type.lower() == "mcq":
            questions.append({
                "q": q,
                "type": "mcq",
                "options": ["Correct answer", "Distractor A", "Distractor B", "Distractor C"],
                "answer_index": 0
            })
        else:
            # true/false fallback
            questions.append({
                "q": q,
                "type": "tf",
                "answer": "True"
            })
    return questions


def _all_match_requested_type(qs: list, requested: str) -> bool:
    """
    Enforce that all questions in qs match the requested type.
    Accept TF naming variants.
    """
    if not isinstance(qs, list) or len(qs) == 0:
        return False
    req = requested.strip().lower()
    want_mcq = req == "mcq"
    want_tf = req in ("true/false", "true_false", "tf", "truefalse", "true false")
    for q in qs:
        qtype = str(q.get("type", "")).strip().lower()
        if want_mcq:
            if qtype != "mcq":
                return False
        elif want_tf:
            if qtype not in ("tf", "truefalse", "true_false"):
                return False
        else:
            # unknown requested type — reject
            return False
    return True


def _render_assessment_html(course_title: str, questions: list, attempts: Optional[int], course_id: str):
    """
    Build the assessment HTML for given questions.
    - questions: list of dicts (see structure above)
    - attempts: optional int, limit of attempts
    - course_id: unique id to store attempts in localStorage
    """
    safe_title = html.escape(course_title)
    total = len(questions)

    # build questions HTML
    q_html = ""
    for i, q in enumerate(questions, start=1):
        q_html += f"<div class='question'><h4>{i}. {html.escape(q['q'])}</h4>\n"
        if q["type"] == "mcq":
            opts = q["options"]
            for oi, opt in enumerate(opts):
                is_correct = "true" if (oi == q.get("answer_index", 0)) else "false"
                q_html += (f"<label><input type='radio' name='q{i}' value='{oi}' data-correct='{is_correct}'> "
                           f"{html.escape(opt)}</label><br>\n")
        else:  # tf
            correct_is_true = (str(q.get("answer", "True")).strip().lower().startswith("t"))
            q_html += (f"<label><input type='radio' name='q{i}' value='True' data-correct='{'true' if correct_is_true else 'false'}'> True</label><br>\n")
            q_html += (f"<label><input type='radio' name='q{i}' value='False' data-correct='{'true' if not correct_is_true else 'false'}'> False</label><br>\n")
        q_html += "</div><hr/>\n"

    attempts_html = ""
    if attempts:
        attempts_html = f"<p>Attempts allowed: {attempts}</p>"

    # JS: compute percent score, handle attempts via localStorage key 'attempts_{course_id}'
    # Includes Reset Attempts UI which either calls RESET_ENDPOINT (if configured) or clears localStorage.
    submit_js = f"""
<script>
const TOTAL = {total};
const COURSE_KEY = 'attempts_{course_id}';
const RESET_ENDPOINT = null; // set to a URL string if you implement server-side reset

function getAttemptsUsed() {{
    const v = localStorage.getItem(COURSE_KEY);
    return v ? parseInt(v, 10) : 0;
}}

function setAttemptsUsed(n) {{
    localStorage.setItem(COURSE_KEY, String(n));
}}

function checkAnswers() {{
    const attemptsAllowed = {attempts if attempts else 'null'};
    let used = getAttemptsUsed();
    if (attemptsAllowed !== null && used >= attemptsAllowed) {{
        document.getElementById('result').innerText = "No attempts left. You have used all allowed attempts.";
        document.getElementById('reset-area').style.display = 'block';
        return false;
    }}

    let correctCount = 0;
    for (let i=1;i<=TOTAL;i++) {{
        let radios = document.getElementsByName('q'+i);
        let chosen = null;
        for (let r=0;r<radios.length;r++) {{
            if (radios[r].checked) {{
                chosen = radios[r];
                break;
            }}
        }}
        if (chosen && chosen.dataset && chosen.dataset.correct === 'true') {{
            correctCount++;
        }}
    }}
    const percent = Math.round((correctCount / TOTAL) * 100);
    if (percent >= 70) {{
        document.getElementById('result').innerText = "Score: " + percent + "%." + " Status: Passed. Your completion has been recorded.";
    }} else {{
        document.getElementById('result').innerText = "Score: " + percent + "%." + " Status: Not passed. You may review the content and attempt again if allowed by the LMS.";
    }}

    // increment attempts used if attempts limit is set
    if (attemptsAllowed !== null) {{
        setAttemptsUsed(used + 1);
        if (used + 1 >= attemptsAllowed) {{
            document.getElementById('reset-area').style.display = 'block';
        }}
    }}
    return false; // prevent actual form submit
}}

function requestRetake() {{
    // If a backend reset endpoint is available, call it:
    if (RESET_ENDPOINT) {{
        fetch(RESET_ENDPOINT, {{ method: 'POST' }})
            .then(res => {{
                if (!res.ok) throw new Error('Reset failed');
                localStorage.removeItem(COURSE_KEY);
                alert('Retake granted. You may attempt the quiz again.');
                document.getElementById('reset-area').style.display = 'none';
            }})
            .catch(e => {{
                alert('Reset request failed. For now local reset will be performed.');
                localStorage.removeItem(COURSE_KEY);
                document.getElementById('reset-area').style.display = 'none';
            }});
    }} else {{
        // No server endpoint configured — do local clear (developer/testing)
        localStorage.removeItem(COURSE_KEY);
        alert('Local attempts cleared. You may attempt again (client-side only).');
        document.getElementById('reset-area').style.display = 'none';
    }}
}}
</script>
"""

    reset_html = """
<div id="reset-area" style="display:none; margin-top:10px;">
  <button type="button" onclick="requestRetake()">Request Retake</button>
  <small style="display:block; color:#555;">()</small>
</div>
"""

    html_page = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Final Assessment - {safe_title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 20px; }}
    .question {{ margin-bottom: 10px; }}
    hr {{ border: 0; border-top: 1px solid #eee; margin: 12px 0; }}
    .submit {{ margin-top: 20px; }}
    #result {{ margin-top: 20px; font-weight: bold; }}
  </style>
</head>
<body>
  <h2>Final Assessment – {"Multiple-Choice Quiz" if any(q['type']=='mcq' for q in questions) else "True / False"}</h2>
  <p>Answer all questions below. Select the best option for each. When finished, click "Submit Quiz & Complete". A minimum score of 70% is required to pass.</p>
  {attempts_html}
  <form onsubmit="return checkAnswers();">
    {q_html}
    <div class="submit">
      <button type="submit">Submit Quiz & Complete</button>
    </div>
    <div id="result"></div>
  </form>
  {reset_html}
  {submit_js}
</body>
</html>
"""
    return html_page


def generate_scorm(course_text: str, output_dir: str = "scorm_package",
                   assessment_type: Optional[str] = None, attempts: Optional[int] = None) -> str:
    """
    Generate a minimal SCORM package with:
      - index.html containing course_text and a link to assessment (if assessment_type provided)
      - assessment.html with 5 questions (MCQ or True/False) generated from GPT (fallback deterministic)
      - imsmanifest.xml listing both resources
    Returns path to zip file.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Save index.html with link to assessment if applicable
    index_html = "<html><head><meta charset='utf-8'><title>Course</title></head><body>"
    index_html += f"<h1>Course Content</h1>\n<pre>{html.escape(course_text)}</pre>\n"
    if assessment_type:
        index_html += f"<hr/><p><a href='assessment.html'>Go to final assessment</a></p>\n"
    index_html += "</body></html>"

    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    # If assessment requested, generate questions via GPT (or fallback) and enforce type
    has_assessment = False
    questions = None
    if assessment_type:
        # Try to get contextual questions from GPT
        questions = _ask_gpt_for_questions(course_text, assessment_type)

        # Enforce requested assessment type exactly. If GPT output doesn't match, discard it.
        if not _all_match_requested_type(questions, assessment_type):
            questions = None

        if not questions:
            # fallback deterministic questions of the requested type
            first_line = course_text.splitlines()[0] if course_text else "Course"
            questions = _fallback_questions(first_line, assessment_type)

        has_assessment = True

        # create a course-unique id for localStorage usage: sanitize folder name
        course_id = os.path.basename(output_dir).replace(' ', '_').lower()
        assessment_html = _render_assessment_html(os.path.basename(output_dir), questions, attempts, course_id)
        with open(os.path.join(output_dir, "assessment.html"), "w", encoding="utf-8") as f:
            f.write(assessment_html)

    # Build manifest with index and optional assessment
    manifest_header = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="com.example.ai-course"
    version="1.0"
    xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
    xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3"
    xmlns:imsss="http://www.imsglobal.org/xsd/imsss"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <organizations default="org1">
    <organization identifier="org1">
      <title>AI Generated Course</title>
"""
    item_index = """
      <item identifier="item1" identifierref="resource1" isvisible="true">
        <title>Lesson 1</title>
      </item>
"""
    item_assessment = ""
    if has_assessment:
        item_assessment = """
      <item identifier="item_assessment" identifierref="resource_assessment" isvisible="true">
        <title>Final Assessment</title>
      </item>
"""

    manifest_middle = """
    </organization>
  </organizations>

  <resources>
    <resource identifier="resource1" type="webcontent" adlcp:scormType="sco" href="index.html">
      <file href="index.html"/>
    </resource>
"""
    resource_assessment = ""
    if has_assessment:
        resource_assessment = """
    <resource identifier="resource_assessment" type="webcontent" adlcp:scormType="sco" href="assessment.html">
      <file href="assessment.html"/>
    </resource>
"""

    manifest_footer = """
  </resources>
</manifest>
"""

    manifest = manifest_header + item_index + item_assessment + manifest_middle + resource_assessment + manifest_footer

    with open(os.path.join(output_dir, "imsmanifest.xml"), "w", encoding="utf-8") as f:
        f.write(manifest)

    # Zip the folder (save zip inside the same folder)
    zip_name = f"{os.path.basename(output_dir)}.zip"
    zip_path = os.path.join(output_dir, zip_name)

    # remove existing zip if present
    if os.path.exists(zip_path):
        try:
            os.remove(zip_path)
        except Exception:
            pass

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, output_dir)
                # don't include the zip itself
                if file == zip_name:
                    continue
                zipf.write(full_path, arcname=arcname)

    return zip_path
