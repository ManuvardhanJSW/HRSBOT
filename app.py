import streamlit as st
import requests
import json
import re
import fitz  # PyMuPDF
import pandas as pd
from docx import Document  # Word support

import csv
from datetime import datetime
import os
import time

# ----------- Usage Summary Logger -----------
def log_usage_summary(log_entry, log_file="usage_log.csv"):
    file_exists = os.path.isfile(log_file)
    with open(log_file, mode='a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=log_entry.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(log_entry)

# ----------- File Extraction -----------
def extract_pdf_text(uploaded_file):
    text = ""
    with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text

def extract_docx_text(uploaded_file):
    try:
        doc = Document(uploaded_file)
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        raise Exception(f"Error reading Word document: {str(e)}")

def extract_text(uploaded_file):
    if uploaded_file.name.lower().endswith(".pdf"):
        return extract_pdf_text(uploaded_file)
    elif uploaded_file.name.lower().endswith(".docx"):
        return extract_docx_text(uploaded_file)
    else:
        raise Exception("Unsupported file format")

# ----------- API CALL -----------
def get_gemini_response(prompt, api_key):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key
    }
    body = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]

# ----------- Prompt -----------
def prepare_prompt(resume_text, jd_text, weights, remark_tone):
    tone_instruction = {
        "Professional": "Use a neutral and formal tone.",
        "Critical": "Be sharply evaluative, pointing out weaknesses clearly.",
        "Blunt": "Give a direct, no-nonsense assessment without sugarcoating."
    }

    return f"""
You are acting as a professional HR Manager at JSW Paints.

Evaluate the following resume against the job description.

Scoring Logic:
1. Experience Match - {weights['experience']}%
2. Skill Match - {weights['skills']}%
3. Education Quality - {weights['education']}%
4. Industry relevance - {weights['industry']}%

Other Rules:
- Deduct 10% if experience < 2 years.
- Direct REJECTION if job-hopping <2 years occurred more than twice.
- Score 0 if working in or ex-JSW, Dulux, Akzo Nobel, Birla Opus.
- For evaluating colleges/universities use NIRF ranking.
- DO NOT reject candidates for working in Asian Paints.

Return ONLY JSON in this format:
{{
  "name": "Full name",
  "score": Final score out of 100,
  "score_breakdown": {{
      "experience": score_from_experience,
      "skills": score_from_skills,
      "education": score_from_education,
      "industry": score_from_industry
  }},
  "education": "Degree and college",
  "experience": "Total relevant years of experience in the given field in JD (e.g. paints/FMCG/chemicals), plus role-wise company breakdown",
  "skills_matched": ["skill1", "skill2"],
  "remark": "30-word summary on fitment and verdict about why they are either Accepted OR Rejected"
}}

Remark Instructions:
- {tone_instruction.get(remark_tone, "Use a professional tone.")}

Resume:
{resume_text}

Job Description:
{jd_text}
"""

# ----------- JD Summary Extraction -----------
def extract_comparison_data(jd_text):
    exp_range = re.search(r"(\d+)\s*(?:to|–|-)\s*(\d+)\s*years", jd_text, re.IGNORECASE)
    if exp_range:
        experience = f"{exp_range.group(1)} to {exp_range.group(2)} years"
    else:
        exp_match = re.search(r"(\d+\+?\s*years?)", jd_text, re.IGNORECASE)
        experience = exp_match.group(1) if exp_match else "Not specified"

    edu_match = re.search(r"qualification\s*[:\-]?\s*([^\n,]+)", jd_text, re.IGNORECASE)
    qualification = edu_match.group(1).strip() if edu_match else "Not specified"

    common_skills = [
        "python", "sql", "excel", "tableau", "power bi", "machine learning",
        "marketing", "branding", "data analysis", "communication", "leadership",
        "sales", "negotiation", "strategy", "presentation", "problem-solving"
    ]
    jd_lower = jd_text.lower()
    skills_found = [skill for skill in common_skills if skill in jd_lower]
    skills = ", ".join(skills_found) if skills_found else "Not specified"

    return experience, skills, qualification

# ----------- JSON Parsing -----------
def parse_json_response(text):
    try:
        json_str = re.search(r"\{.*\}", text, re.DOTALL).group()
        parsed = json.loads(json_str)
        sb = parsed.get("score_breakdown", {})
        for field in ["experience", "skills", "education", "industry"]:
            sb.setdefault(field, 0)
        parsed["score_breakdown"] = sb
        return parsed
    except Exception as e:
        raise ValueError(f"❌ Could not parse JSON from Gemini:\n{text[:500]}...")

# ----------- Score Color -----------
def highlight_score(val):
    try:
        val = int(val)
        if val >= 80:
            return 'background-color: lightgreen'
        elif val >= 60:
            return 'background-color: khaki'
        else:
            return 'background-color: lightcoral'
    except:
        return ''

# ----------- MAIN APP -----------
def main():
    st.title("📄 THE HRminator 💥🤖")

    api_key = st.secrets["GOOGLE_API_KEY"]

    jd = st.text_area("📌 Job Description", placeholder="Paste the job description here...")

    st.markdown("### 🎯 Scoring Criteria Weights (Total must be 100%)")
    col1, col2 = st.columns(2)
    with col1:
        experience_weight = st.number_input("Experience Match %", min_value=0, max_value=100, value=40)
        skills_weight = st.number_input("Skill Match %", min_value=0, max_value=100, value=20)
    with col2:
        education_weight = st.number_input("Education Quality %", min_value=0, max_value=100, value=10)
        industry_weight = st.number_input("Industry Relevance %", min_value=0, max_value=100, value=30)

    st.markdown("### 💬 Remark Style")
    remark_tone = st.selectbox("Choose AI Remark Tone", ["Professional", "Critical", "Blunt"])

    total = experience_weight + skills_weight + education_weight + industry_weight
    if total != 100:
        st.error(f"Total is {total}%. Adjust to equal 100.")
        return

    weights = {
        "experience": experience_weight,
        "skills": skills_weight,
        "education": education_weight,
        "industry": industry_weight
    }

    uploaded_files = st.file_uploader("📎 Upload Resumes (PDF or Word)", type=["pdf", "docx"], accept_multiple_files=True)

    if "results" not in st.session_state:
        st.session_state.results = []

    if st.button("Analyze Resumes"):
        if not jd or not uploaded_files:
            st.warning("Please provide both Job Description and Resumes.")
            return

        start_time = time.time()
        success_count = 0
        failure_count = 0
        error_messages = []


        st.session_state.results = []

        with st.spinner("🔍 Analyzing resumes..."):
            for file in uploaded_files:
                try:
                    resume_text = extract_text(file)
                    prompt = prepare_prompt(resume_text, jd, weights, remark_tone)
                    response_text = get_gemini_response(prompt, api_key)
                    response_json = parse_json_response(response_text)

                    breakdown = response_json.get("score_breakdown", {})
                    breakdown_str = f"Exp: {breakdown.get('experience', 0)}, Skills: {breakdown.get('skills', 0)}, Edu: {breakdown.get('education', 0)}, Ind: {breakdown.get('industry', 0)}"

                    st.session_state.results.append({
                        "filename": file.name,
                        "name": response_json.get("name", "N/A"),
                        "score": int(response_json.get("score", 0)),
                        "education": response_json.get("education", "N/A"),
                        "experience": response_json.get("experience", "N/A"),
                        "skills_matched": ", ".join(response_json.get("skills_matched", [])),
                        "remark": response_json.get("remark", "N/A"),
                        "score_breakdown": breakdown_str
                    })
                    success_count += 1

                except Exception as e:
                    error_msg = f"{file.name} ❌ {str(e)}"
                    st.error(error_msg)
                    error_messages.append(error_msg)
                    failure_count += 1


        duration = round(time.time() - start_time, 2)
        log_usage_summary({
            "timestamp": datetime.now().isoformat(),
            "user_action": "Resume Batch Analysis",
            "number_of_resumes": len(uploaded_files),
            "jd_length_words": len(jd.strip().split()),
            "errors_occurred": failure_count > 0,
            "success_count": success_count,
            "failure_count": failure_count,
            "duration_sec": duration,
            "error_message": "; ".join(error_messages) if error_messages else "None"
        })


    if st.session_state.results:
        st.markdown("### 📌 Job Description Summary")
        exp_required, skills_required, qualification = extract_comparison_data(jd)
        st.info(f"**Expected Experience:** {exp_required}\n\n**Required Education:** {qualification}\n\n**Key Skills Required:** {skills_required}")

        df = pd.DataFrame(st.session_state.results)
        df.sort_values(by="score", ascending=False, inplace=True)

        accepted_df = df[df['score'] >= 60].reset_index(drop=True)
        rejected_df = df[df['score'] < 60].reset_index(drop=True)

        st.markdown("### ✅ First Round: Accepted Candidates")
        st.dataframe(accepted_df.style.applymap(highlight_score, subset=["score"]), use_container_width=True)

        st.markdown("### ❌ First Round: Rejected Candidates")
        st.dataframe(rejected_df.style.applymap(highlight_score, subset=["score"]), use_container_width=True)

    st.markdown("### 📊 Usage Summary Log")
    if os.path.exists("usage_log.csv"):
        usage_df = pd.read_csv("usage_log.csv")
        st.dataframe(usage_df.tail(50), use_container_width=True)
    else:
        st.info("No usage logs found yet.")

if __name__ == "__main__":
    main()
