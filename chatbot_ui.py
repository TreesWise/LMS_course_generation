import streamlit as st
import sys
import os
from io import BytesIO
from datetime import datetime
import pandas as pd
from fpdf import FPDF

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from report_generator.chatbot_logic import extract_entities_from_query, get_learner_status, client
os.makedirs("reports", exist_ok=True)

st.set_page_config(page_title="LMS Progress Chatbot", layout="centered")
st.title("🎓 LMS Learner Progress Chatbot")

# Global GPT helper for format extraction
def extract_format_from_reply(reply_text: str) -> str:
        prompt = f"""
        You are a helpful assistant. A user just said: "{reply_text}"
        Determine if they want the report in "pdf" or "excel".
        Reply ONLY with "pdf", "excel", or "none".
        """
        try:
            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
                messages=[
                    {"role": "system", "content": "You're a format classifier."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            result = response.choices[0].message.content.strip().lower()
            return result if result in ["pdf", "excel"] else "none"
        except Exception as e:
            print("❌ GPT format extraction failed:", str(e))
            return "none"


if "results" not in st.session_state:
    st.session_state.results = None
if "username_filter_required" not in st.session_state:
    st.session_state.username_filter_required = False
if "selected_username" not in st.session_state:
    st.session_state.selected_username = ""
if "generate_ready_data" not in st.session_state:
    st.session_state.generate_ready_data = None

# Step 1: User Query
query = st.text_input("Ask your question (e.g. 'Show learners who completed Python between Jan and June')")

if st.button("🔍 Submit"):
    with st.spinner("Processing..."):
        try:
            st.session_state.results = None
            st.session_state.selected_username = ""
            st.session_state.generate_ready_data = None
            st.session_state.username_filter_required = False

            data = extract_entities_from_query(query)
            username = data.get("username", "").strip().lower()
            course = data.get("course", "").strip()
            status = data.get("status", "").strip().lower()
            start_date = data.get("start_date", "").strip()
            end_date = data.get("end_date", "").strip()

            results = get_learner_status(username, course, status, start_date, end_date)

            if not results:
                st.warning("❌ No matching learners found.")
            else:
                count = len(results)
                if username:
                    st.markdown(f"🧑‍🎓 Found {count} learners matching **{username}**.")
                    st.session_state.username_filter_required = True
                    usernames = list(set(r['username'] for r in results))
                    for i, u in enumerate(usernames, 1):
                        st.markdown(f"{i}. `{u}`")
                    st.session_state.results = results
                else:
                    st.markdown(f"📘 Found {count} learners matching this course or time period.")
                    st.session_state.username_filter_required = False
                    st.session_state.results = results
                    for row in results:
                        st.markdown(f"""
                        <div style=padding:10px;margin:10px 0;border-radius:8px;">
                            👤 <b>{row['username']}</b><br>
                            📘 <b>{row['course']}</b><br>
                            📈 Status: <b>{row['status']}</b><br>
                            📅 Started: {row['course_initiate_date']}<br>
                            ✅ Completed: {row['course_completion_date']}
                        </div>
                        """, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")

# Step 2: If username required, let user type
if st.session_state.username_filter_required and st.session_state.results:
    exact_name = st.text_input("✍️ Type the exact learner name to generate the report")
    if exact_name:
        match = next((r for r in st.session_state.results if r['username'].lower() == exact_name.lower()), None)
        if match:
            st.success(f"✅ Found record for `{exact_name}`. Proceed to generate report.")
            st.session_state.generate_ready_data = [match]
        else:
            st.warning("❌ No exact match found.")

# Step 3: If username not required, generate for all results
if not st.session_state.username_filter_required and st.session_state.results:
    st.info("📤 Would you like a report in PDF or Excel? Type something like 'Send it as PDF'")
    reply = st.text_input("Your reply:")
    if reply:
       
        format = extract_format_from_reply(reply)
        data = st.session_state.results
        df = pd.DataFrame(data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format == "pdf":
            try:
                st.info("📄 Generating PDF...")
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", size=12)
                pdf.cell(200, 10, txt="Learner Progress Report", ln=True, align='C')
                pdf.ln(10)

                for idx, row in df.iterrows():
                    pdf.multi_cell(0, 10, f"Learner: {row['username']}\nCourse: {row['course']}\nStatus: {row['status']}\nStart: {row['course_initiate_date']}\nCompleted: {row['course_completion_date']}")
                    pdf.ln(4)

                pdf_bytes = BytesIO(pdf.output(dest='S').encode('latin1'))
                st.download_button("📥 Download PDF", data=pdf_bytes, file_name=f"learner_report_{timestamp}.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"❌ PDF error: {e}")

        elif format == "excel":
            try:
                st.info("📊 Generating Excel...")
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name="Learners")
                output.seek(0)
                st.download_button("📥 Download Excel", data=output.getvalue(), file_name=f"learner_report_{timestamp}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except Exception as e:
                st.error(f"❌ Excel error: {e}")
        else:
            st.warning("🤖 I couldn't detect a format. Please type 'PDF' or 'Excel'.")

# Step 4: Generate from selected username flow
if st.session_state.generate_ready_data:
    st.info("📤 Would you like a report in PDF or Excel?")
    reply2 = st.text_input("Your reply:", key="second_reply")
    if reply2:
        format = extract_format_from_reply(reply2)
        df = pd.DataFrame(st.session_state.generate_ready_data)
        username = df.iloc[0]['username']
        course = df.iloc[0]['course']
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format == "pdf":
            try:
                st.info("📄 Generating PDF...")
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", size=12)
                pdf.cell(200, 10, txt="Learner Progress Report", ln=True, align='C')
                pdf.ln(10)
                for col in df.columns:
                    pdf.cell(200, 10, txt=f"{col}: {df[col].iloc[0]}", ln=True)

                pdf_bytes = BytesIO(pdf.output(dest='S').encode('latin1'))
                st.download_button("📥 Download PDF", data=pdf_bytes, file_name=f"{username}_{course}_{timestamp}.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"❌ Error: {e}")

        elif format == "excel":
            try:
                st.info("📊 Generating Excel...")
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name="Report")
                output.seek(0)
                st.download_button("📥 Download Excel", data=output.getvalue(), file_name=f"{username}_{course}_{timestamp}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except Exception as e:
                st.error(f"❌ Error: {e}")
        else:
            st.warning("🤖 I couldn't detect a format. Please mention PDF or Excel.")
