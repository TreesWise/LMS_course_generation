import os
import json
from sqlalchemy import create_engine, text
from openai import AzureOpenAI
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import TypedDict, List
import urllib.parse
from sqlalchemy import Column, String, Date
from sqlalchemy.ext.declarative import declarative_base

load_dotenv()

# --------------------------
# Azure GPT client
# --------------------------
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

# --------------------------
# DB Engine for reports
# --------------------------
# def get_db_engine():
#     connection_string = (
#         "mssql+pyodbc://@10.201.1.86,50001/Resume_Parser"
#         "?driver=ODBC+Driver+17+for+SQL+Server"
#         "&trusted_connection=yes"
#     )
#     return create_engine(connection_string)


user=os.getenv("user")
password=os.getenv("password")
server=os.getenv("server")
database=os.getenv("database")
driver=os.getenv("driver")

def get_db_engine():
   
    # Encode credentials for URL safety
    password_enc = urllib.parse.quote_plus(password)
    driver_enc = urllib.parse.quote_plus(driver)

    # Build connection string
    connection_url = (
        f"mssql+pyodbc://{user}:{password_enc}@{server}/{database}"
        f"?driver={driver_enc}"
        f"&Encrypt=yes"
        f"&TrustServerCertificate=no"
        f"&Connection Timeout=30"
    )

    # Create SQLAlchemy engine with health checks
    engine = create_engine(connection_url, pool_pre_ping=True)

    return engine

Base = declarative_base()
import urllib.parse
class UserDetail(Base):
    __tablename__ = 'user_detail'
    __table_args__ = {'schema': 'dbo'}  # Optional: only needed if using SQL Server schema prefix

    username = Column(String(100), primary_key=True, nullable=False)
    completion_status = Column(String(100), nullable=True)
    course = Column(String(100), nullable=True)
    course_initiate_date = Column(Date, nullable=True)
    course_completion_date = Column(Date, nullable=True)


def init_db():
    """
    Initialize Azure SQL database
    """
    try:
        engine = get_db_engine()
        
        # Test connection first
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            print("[DB] Azure SQL connection test successful", flush=True)
        
        # Create tables if they don't exist
        Base.metadata.create_all(bind=engine, checkfirst=True)
        print("[DB] Azure SQL tables initialized", flush=True)
        
    except Exception as e:
        print(f"[DB] Initialization failed: {e}", flush=True)
        # Re-raise the exception to prevent app startup if DB is critical
        raise



# --------------------------
# Entity Extraction (Report Agent)
# --------------------------
def extract_entities_from_query(query: str):
    system_prompt = """
    You are an assistant that extracts structured data from natural language queries 
    about the table `user_detail`.

    The table schema is:
    - username (string)
    - course (string)
    - completion_status (string: 'completed', 'in progress', 'not started')
    - course_completion_date (date)
    - course_initiate_date (date)

    You must output a JSON object with:
    - "username": extracted learner name (or "")
    - "course": extracted course name (or "")
    - "status": one of ["completed", "in progress", "not started"], otherwise ""
    - "start_date": YYYY-MM-DD if a date range mentioned, else ""
    - "end_date": YYYY-MM-DD if a date range mentioned, else ""

    ⚠️ IMPORTANT:
    - Map natural phrases to exact status values:
      * "done", "finished", "already completed" → "completed"
      * "in progress", "ongoing", "currently learning", "progress" → "in progress"
      * "not started", "yet to start", "not begun", "pending" → "not started"
    - Do not output column names like "completion status" as values.
    """
    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        temperature=0.2
    )

    result = response.choices[0].message.content.strip()
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        cleaned = result.strip().strip("```json").strip("```")
        data = json.loads(cleaned)

    # normalize status values
    status_map = {
        "completed": "completed",
        "done": "completed",
        "finished": "completed",
        "already completed": "completed",

        "in progress": "in progress",
        "progress": "in progress",
        "ongoing": "in progress",
        "currently learning": "in progress",

        "not started": "not started",
        "yet to start": "not started",
        "not begun": "not started",
        "pending": "not started",
    }
    status_value = data.get("status", "").lower().strip()
    data["status"] = status_map.get(status_value, "")

    return data

# --------------------------
# Report Generator Query
# --------------------------
def get_learner_status(username="", course="", status="", start_date="", end_date=""):
    engine = get_db_engine()
    filters, params = [], {}

    if username:
        filters.append("LOWER(username) LIKE :username")
        params["username"] = f"%{username.lower()}%"

    if course:
        filters.append("LOWER(course) LIKE :course")
        params["course"] = f"%{course.lower()}%"

    if status:
        filters.append("LOWER(completion_status) = :status")
        params["status"] = status.lower()

    if start_date and end_date:
        filters.append("course_completion_date BETWEEN :start_date AND :end_date")
        params["start_date"] = start_date
        params["end_date"] = end_date

    where_clause = " AND ".join(filters) if filters else "1=1"

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
                "course_completion_date": str(row["course_completion_date"]) if row["course_completion_date"] else None,
                "course_initiate_date": str(row["course_initiate_date"]) if row["course_initiate_date"] else None
            }
            for row in result
        ]

# ====================================================
# Conversational Agent with LangGraph + Memory
# ====================================================
class ChatState(TypedDict):
    messages: List[dict]

def llm_node(state: ChatState):
    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
        messages=state["messages"],
        temperature=0.7
    )
    reply = response.choices[0].message.content.strip()
    state["messages"].append({"role": "assistant", "content": reply})
    return {"messages": state["messages"]}

memory = MemorySaver()
workflow = StateGraph(ChatState)
workflow.add_node("llm", llm_node)
workflow.set_entry_point("llm")
workflow.add_edge("llm", END)
conversation_graph = workflow.compile(checkpointer=memory)

def run_conversation(session_id: str, user_query: str):
    events = conversation_graph.stream(
        {"messages": [{"role": "user", "content": user_query}]},
        config={"configurable": {"thread_id": session_id}},
        stream_mode="values"
    )
    final_state = None
    for state in events:
        final_state = state
    if final_state:
        return final_state["messages"][-1]["content"]
    return "⚠️ Something went wrong."

# ====================================================
# Intent Classifier (Router)
# ====================================================
def classify_intent(query: str) -> str:
    system_prompt = """
    Classify the user query into one of two categories:
    - "report": if the query asks about learner progress, course status, completion, or dates.
    - "conversation": if it's general chat, greetings, or small talk.
    Reply ONLY with "conversation" or "report".
    """
    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        temperature=0
    )
    return response.choices[0].message.content.strip().lower()

















# import os
# import json
# from sqlalchemy import create_engine, text
# from openai import AzureOpenAI
# from dotenv import load_dotenv

# from langgraph.graph import StateGraph, END
# from langgraph.checkpoint.memory import MemorySaver
# from typing import TypedDict, List

# load_dotenv()

# # --------------------------
# # Azure GPT client
# # --------------------------
# client = AzureOpenAI(
#     api_key=os.getenv("AZURE_OPENAI_API_KEY"),
#     api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
#     azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
# )

# # --------------------------
# # DB Engine for reports
# # --------------------------
# def get_db_engine():
#     connection_string = (
#         "mssql+pyodbc://@10.201.1.86,50001/Resume_Parser"
#         "?driver=ODBC+Driver+17+for+SQL+Server"
#         "&trusted_connection=yes"
#     )
#     return create_engine(connection_string)

# # --------------------------
# # Entity Extraction (Report Agent)
# # --------------------------
# def extract_entities_from_query(query: str):
#     system_prompt = """
#             You are an assistant that extracts structured data from natural language queries 
#             about the table `user_detail`.

#             The table schema is:
#             - username (string)
#             - course (string)
#             - completion_status (string: 'completed', 'in progress', 'not started')
#             - course_completion_date (date)
#             - course_initiate_date (date)

#             You must output a JSON object with:
#             - "username": extracted learner name (or "")
#             - "course": extracted course name (or "")
#             - "status": one of ["completed", "in progress", "not started"], otherwise ""
#             - "start_date": YYYY-MM-DD if a date range mentioned, else ""
#             - "end_date": YYYY-MM-DD if a date range mentioned, else ""

#             ⚠️ IMPORTANT:
#             - Map natural phrases to exact status values:
#             * "done", "finished", "already completed" → "completed"
#             * "in progress", "ongoing", "currently learning", "progress" → "in progress"
#             * "not started", "yet to start", "not begun", "pending" → "not started"
#             - Do not output "completion status" as a value.
#             - Only return one of the valid statuses if clearly mentioned.
#         """
#     response = client.chat.completions.create(
#         model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
#         messages=[
#             {"role": "system", "content": system_prompt},
#             {"role": "user", "content": query}
#         ],
#         temperature=0.2
#     )

#     result = response.choices[0].message.content.strip()
#     try:
#         return json.loads(result)
#     except json.JSONDecodeError:
#         cleaned = result.strip().strip("```json").strip("```")
#         return json.loads(cleaned)

# # --------------------------
# # Report Generator Query
# # --------------------------
# def get_learner_status(username="", course="", status="", start_date="", end_date=""):
#     engine = get_db_engine()
#     filters, params = [], {}

#     if username:
#         filters.append("LOWER(username) LIKE :username")
#         params["username"] = f"%{username.lower()}%"

#     if course:
#         filters.append("LOWER(course) = :course")
#         params["course"] = course.lower()

#     if status:
#         filters.append("LOWER(completion_status) = :status")
#         params["status"] = status.lower()

#     if start_date and end_date:
#         filters.append("course_completion_date BETWEEN :start_date AND :end_date")
#         params["start_date"] = start_date
#         params["end_date"] = end_date

#     where_clause = " AND ".join(filters) if filters else "1=1"

#     query = text(f"""
#         SELECT username, course, completion_status, course_completion_date, course_initiate_date
#         FROM user_detail
#         WHERE {where_clause}
#     """)

#     with engine.connect() as conn:
#         print("Generated Query:", query)
#         print("Params:", params)

#         result = conn.execute(query, params).mappings().all()
#         return [
#             {
#                 "username": row["username"],
#                 "course": row["course"],
#                 "status": row["completion_status"],
#                 "course_completion_date": str(row["course_completion_date"]) if row["course_completion_date"] else None,
#                 "course_initiate_date": str(row["course_initiate_date"]) if row["course_initiate_date"] else None
#             }
#             for row in result
#         ]

# # ====================================================
# # 🔹 Conversational Agent with LangGraph + Memory
# # ====================================================

# # 1. Define State
# class ChatState(TypedDict):
#     messages: List[dict]  # history of messages

# # 2. LLM Node
# def llm_node(state: ChatState):
#     response = client.chat.completions.create(
#         model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
#         messages=state["messages"],
#         temperature=0.7
#     )
#     reply = response.choices[0].message.content.strip()
#     # Append assistant reply into memory
#     state["messages"].append({"role": "assistant", "content": reply})
#     return {"messages": state["messages"]}

# # 3. Build LangGraph
# memory = MemorySaver()  # in-memory checkpoint store
# workflow = StateGraph(ChatState)

# workflow.add_node("llm", llm_node)
# workflow.set_entry_point("llm")
# workflow.add_edge("llm", END)

# conversation_graph = workflow.compile(checkpointer=memory)

# # 4. Helper function to run conversation
# def run_conversation(session_id: str, user_query: str):
#     """Run conversational agent with memory per session_id"""
#     events = conversation_graph.stream(
#         {"messages": [{"role": "user", "content": user_query}]},
#         config={"configurable": {"thread_id": session_id}},
#         stream_mode="values"
#     )
#     final_state = None
#     for state in events:
#         final_state = state
#     if final_state:
#         last_msg = final_state["messages"][-1]["content"]
#         return last_msg
#     return "⚠️ Something went wrong."


























# import os
# import json
# from sqlalchemy import create_engine, text
# from openai import AzureOpenAI
# from dotenv import load_dotenv

# load_dotenv()

# # 🔹 Azure GPT-4o setup
# client = AzureOpenAI(
#     api_key=os.getenv("AZURE_OPENAI_API_KEY"),
#     api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
#     azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
# )

# # 🔹 SQLAlchemy engine with trusted connection
# def get_db_engine():
#     connection_string = (
#         "mssql+pyodbc://@10.201.1.86,50001/Resume_Parser"
#         "?driver=ODBC+Driver+17+for+SQL+Server"
#         "&trusted_connection=yes"
#     )
#     return create_engine(connection_string)

# def extract_entities_from_query(query: str):
#     """
#     Uses GPT-4o to extract username and course name from user query.
#     """
#     system_prompt = """
#         You are an assistant that extracts structured data from natural language queries.

#         Return a JSON object with the following keys:
#         - "username": the learner's name if mentioned
#         - "course": the course name if mentioned
#         - "status": 'completed', 'in progress', or 'not started' if specified
#         - "start_date": formatted as YYYY-MM-DD if any date range is mentioned
#         - "end_date": formatted as YYYY-MM-DD if any date range is mentioned

#         If any field is not found, return an empty string for that field.

#         Examples:

#         Input: "Show me Sarah's progress in Python"
#         Output:
#         {
#         "username": "sarah",
#         "course": "python",
#         "status": "",
#         "start_date": "",
#         "end_date": ""
#         }

#         Input: "Show learners who have completed Python between 01st Jan 2025 to 30th June 2025"
#         Output:
#         {
#         "username": "",
#         "course": "python",
#         "status": "completed",
#         "start_date": "2025-01-01",
#         "end_date": "2025-06-30"
#         }

#         Input: "Show me the list of courses Sara has completed between period 01st Jan 2025 to 30th June 2025"
#         Output:
#         {
#         "username": "sara",
#         "course": "",
#         "status": "completed",
#         "start_date": "2025-01-01",
#         "end_date": "2025-06-30"
#         }
#         """

#     response = client.chat.completions.create(
#         model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
#         messages=[
#             {"role": "system", "content": system_prompt},
#             {"role": "user", "content": query}
#         ],
#         temperature=0.2
#     )
#      # Parse and return as JSON
#     result = response.choices[0].message.content.strip()
#     print("\n🧠 GPT Raw Output:")
#     print(result)
#     return json.loads(result)


# def get_learner_status(username="", course="", status="", start_date="", end_date=""):
#     """
#     Returns learner progress based on username, course, status, and completion date range.
#     Uses course_completion_date and course_initiate_date as per DB schema.
#     """

#     print("\n📥 Extracted Query Fields:")
#     print(f"Username: {username}")
#     print(f"Course: {course}")
#     print(f"Status: {status}")
#     print(f"Start Date: {start_date}")
#     print(f"End Date: {end_date}")

#     engine = get_db_engine()
#     filters = []
#     params = {}

#     if username:
#         filters.append("username LIKE :username")
#         params["username"] = f"%{username.lower()}%"

#     if course:
#         filters.append("course = :course")
#         params["course"] = course.lower()

#     if status:
#         filters.append("completion_status = :status")
#         params["status"] = status.capitalize()

#     if start_date and end_date:
#         # You can choose either completion or initiate date depending on intent
#         filters.append("course_completion_date BETWEEN :start_date AND :end_date")
#         params["start_date"] = start_date
#         params["end_date"] = end_date

#     if not filters:
#         return []

#     where_clause = " AND ".join(filters)

#     query = text(f"""
#         SELECT username, course, completion_status, course_completion_date, course_initiate_date
#         FROM user_detail
#         WHERE {where_clause}
#     """)

#     with engine.connect() as conn:
#         result = conn.execute(query, params).mappings().all()
#         return [
#             {
#                 "username": row["username"],
#                 "course": row["course"],
#                 "status": row["completion_status"],
#                 "course_completion_date": row["course_completion_date"].strftime("%Y-%m-%d") if row["course_completion_date"] else None,
#                 "course_initiate_date": row["course_initiate_date"].strftime("%Y-%m-%d") if row["course_initiate_date"] else None
#             }
#             for row in result
#         ]

