import streamlit as st
import google.generativeai as genai
import os
import json
import io
import time
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Placeholder for Canvas environment variables
__app_id = 'c-code-examiner'
__firebase_config = '{}'
__initial_auth_token = ''

# ---------------- Gemini 2.5 Flash Configuration ---------------- #
# Note: In the Canvas environment, the API key is automatically handled.
# We keep this structure for completeness.
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
except:
    pass # Continue without env variable if running in Canvas

def call_gemini(prompt, timeout=60):
    """
    Safely call Gemini 2.5 Flash with content extraction and robust error checking
    for cases where content is blocked (finish_reason 2).
    """
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

        # 1. Check for blocked/empty candidates first
        if not response.candidates:
            st.error("🛑 Gemini generation failed: No candidates returned.")
            return None

        candidate = response.candidates[0]
        
        # 2. Check finish reason if text is missing (handling the reported error)
        # This is the critical fix for the finish_reason: SAFETY error
        if not response.text:
            reason_name = candidate.finish_reason.name
            
            if reason_name == 'SAFETY':
                # This handles the reported 'finish_reason 2' error (SAFETY)
                st.error("🛑 Generation was blocked due to safety policy. Please adjust the input or prompt.")
                return None
            elif reason_name != 'STOP':
                st.error(f"🛑 Generation stopped prematurely. Finish Reason: {reason_name}.")
                return None

        # 3. Safely extract text (if available)
        if response.text:
            return response.text.strip()

        st.warning("⚠️ Gemini 2.5 Flash returned no textual output.")
        return None

    except Exception as e:
        # Catch network errors, timeouts, and other API exceptions
        st.error(f"Gemini 2.5 Flash call failed: {e}")
        return None


# ---------------- Generate Test Cases ---------------- #
def generate_test_cases(c_code: str):
    """Generates test cases from C code using Gemini."""
    st.info("🧠 Generating test cases using Gemini 2.5 Flash...")

    prompt = f"""
You are an expert software tester for C programs.
Analyze the following C source code (shown below in a fenced code block) and
generate a representative set of **test cases** that fully cover its logic,
including edge cases and error conditions.

Each test case must include:
- The exact standard input (as a single string, include \\n where needed)
- The expected standard output (as a string, include \\n)

Return your answer **only** as a JSON array in this format:
[
  {{"input": "5\\n", "expected_output": "120\\n"}},
  {{"input": "3\\n", "expected_output": "6\\n"}}
]

### C Program
```c
{c_code}
```
"""
    response_text = call_gemini(prompt)
    if not response_text:
        return []

    # --- Parse the JSON result safely ---
    try:
        data = json.loads(response_text)
        if isinstance(data, list):
            return data
        else:
            st.warning("⚠️ Gemini response was not a JSON array.")
            return []
    except json.JSONDecodeError:
        st.warning("⚠️ Could not parse Gemini output as JSON. Switching to fallback mode.")
        return []


# ---------------- Simulate Execution & Evaluation ----------------
def simulate_test_execution(c_code: str, test_cases: list):
    """
    Uses Gemini to simulate running the C code against the generated test cases
    and determine the PASS/FAIL status.
    (Note: This function is not used by the current app.py but is here for completeness)
    """
    st.info("🧪 Simulating test execution and marking results (LLM Simulation)...")

    prompt = f"""
You are a highly accurate C program execution simulator.
Analyze the C Code and the provided Test Cases. For each test case, determine if the
'expected_output' exactly matches the output that would be produced by executing
the 'input' against the 'C Code'.

You must return your answer **only** as a JSON array in the following format.
Each object must match the input test case exactly, but add a 'result' key ('PASS' or 'FAIL')
and an 'actual_output' key which must be the output the C code would *actually* produce.
Ensure the 'actual_output' matches the C code's behavior precisely, including any
unexpected or incorrect behavior.

C Code:
```c
{c_code}
```

Test Cases:
{json.dumps(test_cases, indent=2)}

Example output structure:
[
    {{
        "input": "5\\n",
        "expected_output": "120\\n",
        "actual_output": "120\\n",
        "result": "PASS"
    }},
    ...
]
"""
    response_text = call_gemini(prompt)
    if not response_text:
        return []

    try:
        data = json.loads(response_text)
        if isinstance(data, list):
            return data
        else:
            st.warning("⚠️ Simulation response was not a JSON array.")
            return []
    except json.JSONDecodeError:
        st.warning("⚠️ Could not parse simulation output as JSON.")
        return []


# ---------------- Fallback Static Evaluation ----------------
def fallback_code_evaluation(c_code: str):
    """Performs static qualitative evaluation when test-case generation fails."""
    st.info("🧩 Performing static code analysis via Gemini 2.5 Flash...")

    prompt = f"""
You are a senior C language reviewer.
Analyze the code below (in a fenced code block) and produce a structured evaluation:

Program Intent – What it seems to do.

Syntax & Logic Check – Any detected issues or errors.

Completeness – Whether it's runnable or partial.

Input/Output Handling – Clarity and correctness.

Code Quality – Naming, indentation, readability.

Suggestions – Improvements and refactoring advice.

C Code
{c_code}
"""
    report_text = call_gemini(prompt)
    return report_text or "Unable to generate static evaluation report."


# ---------------- Detailed Report ---------------- #
def generate_detailed_report(c_code: str, results: list):
    """Generates a comprehensive report based on code and simulated test results."""
    st.info("📝 Generating detailed report via Gemini 2.5 Flash...")
    prompt = f"""
You are an expert software examiner.
Write a detailed report for this C program using these test results.

C Code:
{c_code}

Test Results (PASS/FAIL included):
{json.dumps(results, indent=2)}

Include:
- Summary of test performance (e.g., 5/7 tests passed)
- Analysis of failed tests and root causes
- Strengths and weaknesses of the code
- Suggested improvements for correctness and style
- Final verdict in plain language
"""
    report_text = call_gemini(prompt)
    return report_text or "Report generation failed."


# ---------------- PDF Report Creation ---------------- #
def create_pdf_report(report_text: str):
    """Generates a PDF from the final report text."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    text_obj = c.beginText(40, 750)
    text_obj.setFont("Helvetica", 10)
    text_obj.setLeading(12)

    y_position = 750
    line_height = 12

    for line in report_text.splitlines():
        # Split long lines for proper wrapping
        while line:
            chunk = line[:100]
            line = line[100:]

            if y_position < 50:
                c.drawText(text_obj)
                c.showPage()
                text_obj = c.beginText(40, 750)
                text_obj.setFont("Helvetica", 10)
                text_obj.setLeading(12)
                y_position = 750

            text_obj.textLine(chunk)
            y_position -= line_height

    c.drawText(text_obj)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf

