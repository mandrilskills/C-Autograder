import json
import os
import time
import concurrent.futures
import streamlit as st
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from langchain_google_genai import ChatGoogleGenerativeAI

# Load .env variables for local testing
load_dotenv()

# -------------------- Gemini Model -------------------- #
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.3,
    max_output_tokens=1024,
)

# ===================================================== #
# Utility Functions
# ===================================================== #

def call_with_timeout(prompt, timeout=40):
    """
    Executes Gemini call with timeout protection.
    """
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(llm.invoke, prompt)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            st.error(f"⏰ Gemini request timed out after {timeout} seconds.")
            return None


def safe_parse_json(text: str):
    """
    Safely parse JSON from Gemini output.
    If it fails, attempts to extract valid substring.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        st.warning("⚠️ Gemini returned unstructured output. Displaying raw output below.")
        st.write(text)
        return []


# ===================================================== #
# 1️⃣ Generate Test Cases with Retry + Timeout
# ===================================================== #

def generate_test_cases(c_code: str):
    """
    Generate valid JSON test cases for the provided C code using Gemini.
    Includes timeout, retry, and auto-fallback triggers.
    """
    st.info("🧠 Generating test cases using Gemini...")

    prompt = f"""
You are an expert C programmer and software tester.
Analyze the following C code and generate up to 5 meaningful test cases.
Each test case should include:
  - "input": the stdin input string
  - "expected_output": the stdout output string
Return ONLY a valid JSON array like this:
[
  {{"input": "5\\n", "expected_output": "120\\n"}},
  {{"input": "0\\n", "expected_output": "1\\n"}}
]

C code:
{c_code}
"""

    response = None
    for attempt in range(3):
        st.write(f"🔁 Attempt {attempt + 1} to contact Gemini...")
        response = call_with_timeout(prompt, timeout=40)
        if response:
            break
        time.sleep(2)

    if not response:
        st.error("❌ Gemini failed to generate test cases after multiple attempts.")
        return None

    raw_output = response.content if hasattr(response, "content") else str(response)
    data = safe_parse_json(raw_output)

    if not data or not isinstance(data, list):
        st.warning("⚠️ Gemini response invalid or empty. Switching to fallback evaluation.")
        return None

    st.success("✅ Test cases generated successfully.")
    return data


# ===================================================== #
# 2️⃣ Fallback Code Evaluation
# ===================================================== #

def fallback_code_evaluation(c_code: str):
    """
    Fallback mode: static qualitative evaluation when test-case generation fails.
    """
    st.info("🧩 Performing static code evaluation via Gemini...")
    prompt = f"""
You are a senior C programming instructor and code reviewer.
Analyze the following C program and produce a structured evaluation covering:

1. Program Intent – What the code attempts to do.
2. Syntax & Logic Check – Syntax issues or logical flaws.
3. Completeness – Is it functional or partial?
4. Input/Output Handling – How user I/O is managed.
5. Code Quality – Naming, readability, indentation, clarity.
6. Recommendations – Improvements and missing cases.

Return your analysis as a descriptive paragraph.
C Code:
{c_code}
"""

    for attempt in range(2):
        st.write(f"🧠 Static evaluation attempt {attempt + 1}...")
        response = call_with_timeout(prompt, timeout=50)
        if response:
            st.success("✅ Static evaluation completed successfully.")
            return response.content if hasattr(response, "content") else str(response)
        time.sleep(2)

    st.error("⚠️ Fallback evaluation failed after multiple attempts.")
    return "Unable to perform static evaluation."


# ===================================================== #
# 3️⃣ Generate Detailed Report
# ===================================================== #

def generate_detailed_report(c_code: str, test_results: list):
    """
    Summarize program performance based on test results.
    """
    st.info("📝 Generating detailed performance report...")

    prompt = f"""
You are a programming examiner.
You are given the student's C code and the corresponding test case results.

C Code:
{c_code}

Test Results (JSON):
{json.dumps(test_results, indent=2)}

Prepare a detailed report including:
1. Overall correctness summary
2. Logical or syntax errors
3. Output mismatches
4. Missed edge cases
5. Final comments and improvement suggestions
"""

    response = call_with_timeout(prompt, timeout=60)
    if not response:
        return "Report generation timed out. Partial results only."

    return response.content if hasattr(response, "content") else str(response)


# ===================================================== #
# 4️⃣ Generate PDF Report
# ===================================================== #

def create_pdf_report(report_text: str, filename: str = "grading_report.pdf"):
    """
    Create a downloadable PDF report for user feedback.
    """
    os.makedirs("outputs", exist_ok=True)
    pdf_path = os.path.join("outputs", filename)

    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    y = height - 50
    c.setFont("Helvetica", 11)

    for line in report_text.split("\n"):
        c.drawString(40, y, line)
        y -= 15
        if y < 40:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 11)

    c.save()
    return pdf_path
