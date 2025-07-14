import google.generativeai as genai
import PyPDF2 as pdf
from docx import Document
import json
import re

def configure_genai(api_key):
    """Configure the Generative AI API with error handling."""
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        raise Exception(f"Failed to configure Generative AI: {str(e)}")

def get_gemini_response(prompt):
    """Generate a response using Gemini with enhanced error handling and response validation."""
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)

        if not response or not response.text:
            raise Exception("Empty response received from Gemini")

        try:
            response_json = json.loads(response.text)

            required_fields = ["name", "score", "education", "experience", "skills_matched", "remark"]
            for field in required_fields:
                if field not in response_json:
                    raise ValueError(f"Missing required field: {field}")

            return response.text

        except json.JSONDecodeError:
            json_pattern = r'\{.*\}'
            match = re.search(json_pattern, response.text, re.DOTALL)
            if match:
                return match.group()
            else:
                raise Exception("Could not extract valid JSON response")

    except Exception as e:
        raise Exception(f"Error generating response: {str(e)}")

# ----------------- Resume Text Extraction -----------------

def extract_pdf_text(uploaded_file):
    """Extract text from a PDF file with error handling."""
    try:
        reader = pdf.PdfReader(uploaded_file)
        if len(reader.pages) == 0:
            raise Exception("PDF file is empty")

        text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)

        if not text:
            raise Exception("No text could be extracted from the PDF")

        return " ".join(text)

    except Exception as e:
        raise Exception(f"Error extracting PDF text: {str(e)}")

def extract_docx_text(uploaded_file):
    """Extract text from a Word (.docx) file with error handling."""
    try:
        doc = Document(uploaded_file)
        return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    except Exception as e:
        raise Exception(f"Error extracting DOCX text: {str(e)}")

def extract_text(uploaded_file):
    """Auto-detect and extract text from supported resume formats (PDF, DOCX)."""
    filename = uploaded_file.name.lower()
    if filename.endswith(".pdf"):
        return extract_pdf_text(uploaded_file)
    elif filename.endswith(".docx"):
        return extract_docx_text(uploaded_file)
    else:
        raise Exception("Unsupported file type. Only PDF and DOCX are allowed.")

# ----------------- Prompt Generator -----------------

def prepare_prompt(resume_text, job_description, weights, remark_tone="Professional"):
    """Prepare a structured prompt for Gemini using dynamic weights."""
    if not resume_text or not job_description:
        raise ValueError("Resume text and job description cannot be empty")

    tone_instruction = {
        "Professional": "Use a neutral and formal tone.",
        "Critical": "Be sharply evaluative, pointing out weaknesses clearly.",
        "Blunt": "Give a direct, no-nonsense assessment without sugarcoating."
    }

    prompt_template = f"""
You are acting as a professional HR Manager at JSW Paints with deep expertise in:
- Category and Brand Management
- Marketing Strategy
- Product Lifecycle Management
- Stakeholder Communication
- Filtering out candidates and giving proper remarks

Evaluate the following resume against the job description.

Scoring Logic:
1. Experience Match - {weights['experience']}%
2. Skill Match - {weights['skills']}%
3. Education Quality - {weights['education']}%
4. Industry relevance - {weights['industry']}%

Strict Rules:
- Deduct 10% if total experience < 2 years.
- Reject candidate (score 0) if job-hopping occurred more than twice (less than 2 years per company).
- Reject if currently working at Dulux, Akzo Nobel, or Birla Opus.
- Reject if previously worked at JSW (Ex-JSW).
- DO NOT score based on mandatory skills. That is handled in a separate step.

Remark Style:
- {tone_instruction.get(remark_tone, "Use a professional tone.")}

Return ONLY this strict JSON format:
{{
  "name": "Full name of the candidate",
  "score": Final score out of 100,
  "education": "Degree and college",
  "experience": "Total relevant years of experience in the given field in JD (e.g. paints/FMCG/chemicals), plus role-wise company breakdown"
  "skills_matched": ["list", "of", "skills"],
  "remark": "Short 30-word verdict on why selected or not"
}}

Resume:
{resume_text}

Job Description:
{job_description}
"""
    return prompt_template.strip()
