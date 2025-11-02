import json
import streamlit as st
from dotenv import load_dotenv
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from langchain_google_genai import ChatGoogleGenerativeAI

# Load environment variables
load_dotenv()

# Initialize Gemini LLM
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.3,
    max_output_tokens=1024
)

# ---------- Utility: Safe JSON Parsing ---------- #
def safe_parse_json(text: str):
    """Safely parse Gemini LLM output into JSON."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find('['), text.rfind(']')
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        st.warning("⚠️ Gemini returned unstructured data. Displaying raw output below.")
        st.write(text)
        return []


# ---------- 1️⃣ Generate Test Cases ---------- #
def generate_test_cases(c_code: str):
    """Generate structured test cases for the provided C code."""
    st.info("🧠 Generating test cases using Gemini...")
    prompt = f"""
You are an expert C programmer and software tester.
Analyze the following C code and generate 5 meaningful test cases.
Each test case should include:
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
            st.warning("⚠️ Unable to generate valid test cases.")
            return None

        st.success("✅ Test cases generated successfully.")
        return data

    except Exception as e:
        st.error(f"Error generating test cases: {e}")
        return None


# ---------- 2️⃣ Fallback Evaluation System ---------- #
def fallback_code_evaluation(c_code: str):
    """Perform qualitative code evaluation when no test cases can be generated."""
    st.info("🧩 Performing static code evaluation via Gemini...")
    prompt = f"""
You are a senior C programming instructor and code reviewer.
Analyze the following C program and produce a structured evaluation covering:

1. **Program Intent** – What the program seems to do.
2. **Syntax & Logic Check** – Identify syntax errors or logical flaws.
3. **Completeness** – Is it functional or incomplete?
4. **Input/Output Handling** – How well does it manage user I/O?
5. **Code Quality** – Naming, readability, indentation, clarity.
6. **Recommendations** – Improvements, missing edge cases, optimization hints.

Return your analysis in a well-written paragraph form.
C Code:
{c_code}
"""
    try:
        response = llm.invoke(prompt)
        report = response.content if hasattr(response, "content") else str(response)
        st.success("✅ Static evaluation completed.")
        return report
    except Exception as e:
        st.error(f"Fallback evaluation failed: {e}")
        return "Unable to evaluate the code."


# ---------- 3️⃣ Generate Detailed Report ---------- #
def generate_detailed_report(c_code: str, test_results: list):
    """Create a descriptive evaluation report based on code and test results."""
    st.info("📝 Generating final report...")
    prompt = f"""
You are a programming examiner.
You are given a student's C code and the test results.

C Code:
{c_code}

Test Results:
{json.dumps(test_results, indent=2)}

Write a detailed evaluation report including:
1. Summary of correctness
2. Errors or deviations in output
3. Logical or syntactical issues
4. Missed edge cases
5. Final remarks and feedback
"""
    try:
        response = llm.invoke(prompt)
        return response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        st.error(f"Error generating report: {e}")
        return "Report generation failed."


# ---------- 4️⃣ Create PDF Report ---------- #
def create_pdf_report(report_text: str, filename: str = "grading_report.pdf"):
    """Generate a downloadable PDF report."""
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
