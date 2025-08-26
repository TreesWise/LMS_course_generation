import os
import json
from sqlalchemy import create_engine, text
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

# 🔹 Azure GPT-4o setup
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

# 🔹 SQLAlchemy engine with trusted connection
def get_db_engine():
    connection_string = (
        "mssql+pyodbc://@10.201.1.86,50001/Resume_Parser"
        "?driver=ODBC+Driver+17+for+SQL+Server"
        "&trusted_connection=yes"
    )
    return create_engine(connection_string)

def extract_entities_from_query(query: str):
    """
    Uses GPT-4o to extract username and course name from user query.
    """
    system_prompt = """
        You are an assistant that extracts structured data from natural language queries.

        Return a JSON object with the following keys:
        - "username": the learner's name if mentioned
        - "course": the course name if mentioned
        - "status": 'completed', 'in progress', or 'not started' if specified
        - "start_date": formatted as YYYY-MM-DD if any date range is mentioned
        - "end_date": formatted as YYYY-MM-DD if any date range is mentioned

        If any field is not found, return an empty string for that field.

        Examples:

        Input: "Show me Sarah's progress in Python"
        Output:
        {
        "username": "sarah",
        "course": "python",
        "status": "",
        "start_date": "",
        "end_date": ""
        }

        Input: "Show learners who have completed Python between 01st Jan 2025 to 30th June 2025"
        Output:
        {
        "username": "",
        "course": "python",
        "status": "completed",
        "start_date": "2025-01-01",
        "end_date": "2025-06-30"
        }

        Input: "Show me the list of courses Sara has completed between period 01st Jan 2025 to 30th June 2025"
        Output:
        {
        "username": "sara",
        "course": "",
        "status": "completed",
        "start_date": "2025-01-01",
        "end_date": "2025-06-30"
        }
        """

    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        temperature=0.2
    )
     # Parse and return as JSON
    result = response.choices[0].message.content.strip()
    print("\n🧠 GPT Raw Output:")
    print(result)
    return json.loads(result)


def get_learner_status(username="", course="", status="", start_date="", end_date=""):
    """
    Returns learner progress based on username, course, status, and completion date range.
    Uses course_completion_date and course_initiate_date as per DB schema.
    """

    print("\n📥 Extracted Query Fields:")
    print(f"Username: {username}")
    print(f"Course: {course}")
    print(f"Status: {status}")
    print(f"Start Date: {start_date}")
    print(f"End Date: {end_date}")

    engine = get_db_engine()
    filters = []
    params = {}

    if username:
        filters.append("username LIKE :username")
        params["username"] = f"%{username.lower()}%"

    if course:
        filters.append("course = :course")
        params["course"] = course.lower()

    if status:
        filters.append("completion_status = :status")
        params["status"] = status.capitalize()

    if start_date and end_date:
        # You can choose either completion or initiate date depending on intent
        filters.append("course_completion_date BETWEEN :start_date AND :end_date")
        params["start_date"] = start_date
        params["end_date"] = end_date

    if not filters:
        return []

    where_clause = " AND ".join(filters)

    query = text(f"""
        SELECT username, course, completion_status, course_completion_date, course_initiate_date
        FROM user_detail
        WHERE {where_clause}
    """)

    with engine.connect() as conn:
        result = conn.execute(query, params).mappings().all()
        return [
            {
                "username": row["username"],
                "course": row["course"],
                "status": row["completion_status"],
                "course_completion_date": row["course_completion_date"].strftime("%Y-%m-%d") if row["course_completion_date"] else None,
                "course_initiate_date": row["course_initiate_date"].strftime("%Y-%m-%d") if row["course_initiate_date"] else None
            }
            for row in result
        ]

