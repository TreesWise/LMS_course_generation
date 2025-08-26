import os
import streamlit as st
import requests

API_URL = "http://localhost:8000"

st.set_page_config(page_title="AI Syllabus Builder", layout="centered")
st.title("📘 AI-Powered Syllabus to Course Generator")

# --- Syllabus Input Form ---
st.markdown("## ✍️ Create Syllabus")
topic = st.text_input("📘 Topic Name")
audience = st.selectbox("🎯 Target Audience", ["Beginner", "Intermediate", "Advanced"])
duration = st.number_input("🗓 Duration (weeks)", min_value=1, max_value=52)
outcomes = st.text_area("🎓 Learning Outcomes", "Understand the core concepts.")
content_types = st.multiselect("🧩 Preferred Content", ["Text", "Video", "Quiz", "Interactive"])
references = st.text_input("🔗 References (URL or text)")

if st.button("🚀 Generate Syllabus"):
    with st.spinner("Generating syllabus..."):
        payload = {
            "topic": topic,
            "audience": audience,
            "duration": duration,
            "outcomes": outcomes,
            "content_types": content_types,
            "references": references
        }
        res = requests.post(f"{API_URL}/generate_syllabus/", json=payload)
        if res.status_code == 200:
            data = res.json()
            st.success("✅ Syllabus generated!")
            st.text_area("📋 Syllabus", data["syllabus"], height=300)
        else:
            st.error("❌ Failed to generate syllabus.")

# --- View Generated Syllabi ---
st.markdown("## 🧾 Generated Syllabus")
res = requests.get(f"{API_URL}/generated_syllabus/")
if res.status_code == 200:
    for item in res.json():
        with st.expander(f"📘 {item['syllabus_name']}"):
           # Editable syllabus preview
            edited_syllabus = st.text_area(
                "📝 Edit Syllabus",
                value=item["syllabus"],
                height=200,
                key=f"edit_{item['syllabus_name']}"
            )

            # Save button
            if st.button("💾 Save Edited Syllabus", key=f"save_{item['syllabus_name']}"):
                save_res = requests.post(
                    f"{API_URL}/save_edited_syllabus/",
                    json={
                        "syllabus_name": item["syllabus_name"],
                        "syllabus_text": edited_syllabus
                    }
                )
                if save_res.status_code == 200:
                    st.success("✅ Syllabus saved successfully.")
                else:
                    st.error("❌ Failed to save syllabus.")

            # Verify button
            if st.button(f"✅ Verify Syllabus", key=f"verify_{item['syllabus_name']}"):
                verify_res = requests.post(f"{API_URL}/verify_syllabus/{item['syllabus_name']}")
                if verify_res.status_code == 200:
                    st.success("✅ Syllabus verified")
                    st.rerun()
                else:
                    st.error("❌ Verification failed")


# === Generate Course from Verified Syllabus ===
st.markdown("## 📚 Generate Course from Verified Syllabus")

res = requests.get(f"{API_URL}/generated_syllabus/")
verified_list = []

# Only include verified syllabi
for item in res.json():
    name = item['syllabus_name']
    if os.path.exists(f"verified_syllabus/{name}/syllabus.txt"):
        verified_list.append(name)



if verified_list:
    selected = st.selectbox(
        "📑 Verified Syllabus",
        verified_list,
        key="select_verified_syllabus"
    )

    if st.button("🚀 Generate Detailed Course", key=f"generate_btn_{selected}"):
        with st.spinner("Generating full course content..."):
            course_res = requests.post(f"{API_URL}/generate_content_from_syllabus/{selected}")
            if course_res.status_code == 200:
                data = course_res.json()
                st.success("✅ Course content generated!")
                st.text_area("📘 Full Course Outline", data["outline"], height=300)
                st.markdown(
                    f'<a href="{data["scorm_url"]}" target="_blank">'
                    f'<button style="margin-top:10px;">🔗 Open SCORM in New Tab</button></a>',
                    unsafe_allow_html=True
                )
            else:
                st.error("❌ Failed to generate course content.")
else:
    st.info("ℹ️ Please verify a syllabus before generating the full course.")

# --- View Final Course Content ---
st.markdown("## 📦 Final Generated Courses")

res = requests.get(f"{API_URL}/final_courses/")
if res.status_code == 200:
    if res.json():
        for course in res.json():
            with st.expander(f"📘 {course['course_name']}"):
                st.text_area("📋 Course Outline", course["outline"], height=250, key=f"final_{course['course_name']}")
                st.markdown(
                    f'<a href="{course["scorm_url"]}" target="_blank">'
                    f'<button style="margin-top:10px;">🔗 Open SCORM in New Tab</button></a>',
                    unsafe_allow_html=True
                )
    else:
        st.info("ℹ️ No final courses available yet.")
else:
    st.error("❌ Failed to load final courses.")



# --- Search or Filter Final Courses ---
st.markdown("## 🔎 Search or Filter Final Courses")

search_mode = st.radio("Choose search type", ["Search by Content/Name", "Filter by Course Name"], horizontal=True)

if search_mode == "Search by Content/Name":
    query = st.text_input("🔍 Enter search keyword")
    if st.button("🔎 Search Final Courses"):
        if query:
            res = requests.get(f"{API_URL}/final_courses/search", params={"query": query})
            if res.status_code == 200:
                results = res.json()
                if results:
                    for course in results:
                        with st.expander(f"📘 {course['course_name']}"):
                            st.text_area("📋 Outline", course["outline"], height=250, key=f"search_{course['course_name']}")
                            st.markdown(
                                f'<a href="{course["scorm_url"]}" target="_blank">'
                                f'<button style="margin-top:10px;">🔗 Open SCORM in New Tab</button></a>',
                                unsafe_allow_html=True
                            )
                else:
                    st.warning("No results found.")
            else:
                st.error("Failed to fetch results.")

else:
    filter_text = st.text_input("🔎 Enter filter keyword (e.g. beginner, node, python)")
    if st.button("🔽 Filter Final Courses"):
        if filter_text:
            res = requests.get(f"{API_URL}/final_courses/filter", params={"filter": filter_text})
            if res.status_code == 200:
                results = res.json()
                if results:
                    for course in results:
                        with st.expander(f"📘 {course['course_name']}"):
                            st.text_area("📋 Outline", course["outline"], height=250, key=f"filter_{course['course_name']}")
                            st.markdown(
                                f'<a href="{course["scorm_url"]}" target="_blank">'
                                f'<button style="margin-top:10px;">🔗 Open SCORM in New Tab</button></a>',
                                unsafe_allow_html=True
                            )
                else:
                    st.warning("No matching courses.")
            else:
                st.error("Failed to fetch filtered results.")
