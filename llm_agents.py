import json
import streamlit as st
from dotenv import load_dotenv
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Load environment variables (for local dev)
load_dotenv()

# Import Gemini LLM
from langchain_google_genai import ChatGoogleGenerativeAI

# Initialize Gemini model
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.3,
    max_output_tokens=1024
)

# ---------- Utility: Safe JSON Parsing ---------- #
def safe_parse_json(text: str):
    """
    Attempts to safely parse Gemini LLM output into JSON.
    If JSON decoding fails, tries to extract JSON substring.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find('['), text.rfind(']')
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        st.error("⚠️ Gemini returned invalid JSON. Displaying raw output below:")
        st.write(text)
        return []


# ---------- 1️⃣ Generate Test Cases ---------- #
def generate_test_cases(c_code: str):
    """
    Uses Gemini to generate valid JSON test cases for the provided C code.
    Each test case should contain 'input' and 'expected_output'.
    """
    st.info("🧠 Generating test cases using Gemini...")
    prompt = f"""
You are an expert C programmer and software tester.
Analyze the following C code and generate 5 meaningful test cases.
Each test case should have:
  - "input": simulated stdin input (string)
  - "expected_output": the exact expected stdout output (string)

Return ONLY a valid JSON array like this:
[
  {{"input": "5\\n", "expected_output": "120\\n"}},
  {{"input": "0\\n", "expected_output": "1\\n"}}
]

C code:
{c_code}
"""

    try:
        response = llm.invoke(prompt)
        raw_output = response.content if hasattr(response, "content") else str(response)
        data = safe_parse_json(raw_output)

        if not data or not isinstance(data, list):
            st.error("❌ No valid test cases generated. Please try again.")
            st.write("Model output:", raw_output)
            return []

        st.success("✅ Test cases generated successfully.")
        return data

    except Exception as e:
        st.error(f"Error generating test cases: {e}")
        return []


# ---------- 2️⃣ Generate Detailed Report ---------- #
def generate_detailed_report(c_code: str, test_results: list):
    """
    Summarizes the performance of the submitted code based on test results.
    """
    prompt = f"""
You are an expert code reviewer and programming instructor.
You are given the original C code and its grading results.

C Code:
{c_code}

Test Results (JSON):
{json.dumps(test_results, indent=2)}

Write a detailed report that includes:
1. Summary of overall correctness
2. Logical or syntax issues (if any)
3. Edge cases missed
4. Recommendations for improvement
"""
    try:
        response = llm.invoke(prompt)
        return response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        st.error(f"Error generating report: {e}")
        return "Report generation failed."


# ---------- 3️⃣ Create PDF Report ---------- #
def create_pdf_report(report_text: str, filename: str = "grading_report.pdf"):
    """
    Generates a downloadable PDF report using ReportLab.
    """
    pdf_path = os.path.join("outputs", filename)
    os.makedirs("outputs", exist_ok=True)

    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    y = height - 50
    c.setFont("Helvetica", 11)
    for line in report_text.split("\n"):
        c.drawString(40, y, line)
        y -= 15
        if y < 40:  # new page
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 11)
    c.save()
    return pdf_path
