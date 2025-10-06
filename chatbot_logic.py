import os
from sqlalchemy import create_engine, text
from openai import AzureOpenAI
from dotenv import load_dotenv
from sqlalchemy import Column, String, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


load_dotenv()
 
# --------------------------
# Azure GPT client (future use if LLM needed)
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




# ------------------------------------------------------------------------------
# ORM models
# ------------------------------------------------------------------------------
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


# ====================================================
# 1. Static Course Report Categories
# ====================================================
def get_report_categories():
    return ["allocated", "pending", "completed", "overdue", "in progress", "not started"]
 
 
# ====================================================
# 2. Course list by status
# ====================================================
def get_courses_by_status(status: str):
    valid_status = ["allocated", "pending", "completed", "overdue", "in progress", "not started"]
    if status.lower() not in valid_status:
        return {"error": "invalid input"}
 
    engine = get_db_engine()
    query = text("""
        SELECT DISTINCT course
        FROM user_detail
        WHERE LOWER(completion_status) = :status
    """)
    with engine.connect() as conn:
        result = conn.execute(query, {"status": status.lower()}).mappings().all()
        courses = [row["course"] for row in result]
        return {"status": status.lower(), "courses": courses}
 
 
# ====================================================
# 3. Selection Handler (course or learner + status)
# ====================================================
def handle_selection(course: str, learner: str, status: str = ""):
    if not course and not learner:
        return {"error": "invalid input"}
 
    engine = get_db_engine()
    filters, params = [], {}
 
    if course:
        filters.append("LOWER(course) LIKE :course")
        params["course"] = f"%{course.lower()}%"
 
    if learner:
        filters.append("LOWER(username) LIKE :learner")
        params["learner"] = f"%{learner.lower()}%"
 
    if status:
        filters.append("LOWER(completion_status) = :status")
        params["status"] = status.lower()
 
    where_clause = " AND ".join(filters) if filters else "1=1"
 
    query = text(f"""
        SELECT username, course, completion_status, course_completion_date, course_initiate_date
        FROM user_detail
        WHERE {where_clause}
    """)
 
    with engine.connect() as conn:
        result = conn.execute(query, params).mappings().all()
        if not result:
            return {"error": "invalid input"}
 
        return {
            "results": [
                {
                    "username": row["username"],
                    "course": row["course"],
                    "status": row["completion_status"],
                    "course_completion_date": str(row["course_completion_date"]) if row["course_completion_date"] else None,
                    "course_initiate_date": str(row["course_initiate_date"]) if row["course_initiate_date"] else None
                }
                for row in result
            ]
        }
 