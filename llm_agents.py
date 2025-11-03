import streamlit as st
import google.generativeai as genai
import os
import json
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# ---------------- Gemini 2.5 Flash Configuration ---------------- #
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def call_gemini(prompt, timeout=30):
    """Safely call Gemini 2.5 Flash with content extraction."""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            prompt,
            request_options={"timeout": timeout},
            generation_config={
                "temperature": 0.4,
                "max_output_tokens": 2048,
            },
        )

        # --- Safely extract text ---
        if hasattr(response, "text") and response.text:
            return response.text.strip()

        # Newer SDK: sometimes only .candidates exist
        if hasattr(response, "candidates") and response.candidates:
            parts = response.candidates[0].content.parts
            if parts and hasattr(parts[0], "text"):
                return parts[0].text.strip()

        # If no text at all
        st.warning("⚠️ Gemini 2.5 Flash returned no textual output.")
        return None

    except Exception as e:
        st.error(f"Gemini 2.5 Flash call failed: {e}")
        return None



# ---------------- Generate Test Cases ---------------- #
def generate_test_cases(c_code: str):
    st.info("🧠 Generating test cases using Gemini 2.5 Flash...")
    prompt = f"""
You are a professional C language tester.
Generate diverse test cases for the following program.
Each test must include valid input and the expected output.

Return output strictly as a JSON array of objects in this format:
[
  {{"input": "5\\n", "expected_output": "120\\n"}}
]

C Program:
{c_code}
"""
    response_text = call_gemini(prompt)
    if not response_text:
        return []

    try:
        data = json.loads(response_text)
        if isinstance(data, list):
            return data
        else:
            st.warning("⚠️ Gemini response not valid JSON array.")
            return []
    except json.JSONDecodeError:
        st.warning("⚠️ Could not parse Gemini output. Switching to fallback mode.")
        return []


# ---------------- Fallback Static Evaluation ---------------- #
def fallback_code_evaluation(c_code: str):
    st.info("🧩 Performing static code analysis via Gemini 2.5 Flash...")
    prompt = f"""
Analyze the following C code and produce a structured evaluation:

1. Program Intent – What it seems to do.
2. Syntax & Logic Check – Any errors or issues.
3. Completeness – Is it runnable / partial / missing I/O?
4. Input & Output Handling.
5. Code Quality – Naming, readability, indentation.
6. Suggestions for improvement.

C Code:
{c_code}
"""
    report_text = call_gemini(prompt)
    return report_text or "Unable to generate static evaluation report."


# ---------------- Detailed Report ---------------- #
def generate_detailed_report(c_code: str, results: list):
    st.info("📝 Generating detailed report via Gemini 2.5 Flash...")
    prompt = f"""
You are an expert software examiner.
Write a detailed report for this C program using these test results.

C Code:
{c_code}

Test Results:
{json.dumps(results, indent=2)}

Include:
- Summary of test performance
- Strengths and weaknesses
- Suggested improvements
- Final verdict in plain language
"""
    report_text = call_gemini(prompt)
    return report_text or "Report generation failed."


# ---------------- PDF Report Creation ---------------- #
def create_pdf_report(report_text: str):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    text_obj = c.beginText(40, 750)
    text_obj.setFont("Helvetica", 10)

    for line in report_text.splitlines():
        text_obj.textLine(line[:110])  # limit line length for layout
    c.drawText(text_obj)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf
