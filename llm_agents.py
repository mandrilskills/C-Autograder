import streamlit as st
import google.generativeai as genai
import os
import json
import io
import time
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from typing import Dict, List

# Placeholder for Canvas environment variables
__app_id = 'c-code-examiner'
__firebase_config = '{}'
__initial_auth_token = ''

# ---------------- Gemini 2.5 Flash Configuration ---------------- #
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
except:
    pass 

def call_gemini(prompt, timeout=60):
    """
    Safely call Gemini 2.5 Flash with content extraction and robust error checking
    for cases where content is blocked (finish_reason 2/SAFETY).
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

        if not response.candidates:
            st.error("🛑 Gemini generation failed: No candidates returned.")
            return None

        candidate = response.candidates[0]
        
        if not response.text:
            reason_name = candidate.finish_reason.name
            
            if reason_name == 'SAFETY':
                st.error("🛑 Generation was blocked due to safety policy. Please adjust the input or prompt.")
                return None
            elif reason_name != 'STOP':
                st.error(f"🛑 Generation stopped prematurely. Finish Reason: {reason_name}.")
                return None

        if response.text:
            return response.text.strip()

        st.warning("⚠️ Gemini 2.5 Flash returned no textual output.")
        return None

    except Exception as e:
        st.error(f"Gemini 2.5 Flash call failed: {e}")
        return None


# ---------------- Generate Test Cases (JSON for Execution Agent) ---------------- #
def generate_test_cases(c_code: str) -> List[Dict[str, str]]:
    """
    Generates test cases from C code using Gemini, returning structured JSON 
    required by the LangGraph execution agent.
    """
    st.info("🧠 Generating structured test cases using Gemini 2.5 Flash...")

    prompt = f"""
You are an expert software tester for C programs.
Analyze the following C source code and generate a representative set of 
**test cases** that fully cover its logic and edge cases.

Each test case must include:
- The exact standard input (as a single string, include \\n where needed)
- The expected standard output (as a string, include \\n)

Return your answer **only** as a JSON array in this format:
[
  {{"input": "5\\n", "output": "120\\n"}},
  {{"input": "3\\n", "output": "6\\n"}}
]
Note: Use the key "output" for the expected result.

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
        # Clean up common markdown blocks that often wrap LLM JSON output
        json_string = response_text.strip()
        if json_string.startswith("```json"):
            json_string = json_string[7:].strip()
        if json_string.endswith("```"):
            json_string = json_string[:-3].strip()
            
        data = json.loads(json_string)
        if isinstance(data, list):
            # Basic validation for required keys
            if all("input" in d and "output" in d for d in data):
                 return data
            else:
                 st.warning("⚠️ Test cases parsed but missing 'input' or 'output' keys.")
                 return []
        else:
            st.warning("⚠️ Gemini response was not a JSON array.")
            return []
    except json.JSONDecodeError as e:
        st.warning(f"⚠️ Could not parse Gemini output as JSON. Execution testing will be skipped. Error: {e}")
        return []


# ---------------- Detailed Report (from LangGraph Analysis) ---------------- #
def generate_detailed_report(c_code: str, structured_results: Dict):
    """
    Generates a final, comprehensive report for the user based on the
    structured results from the LangGraph execution pipeline.
    """
    st.info("📝 Generating final human-readable report via Gemini 2.5 Flash...")
    
    # Format the structured results from LangGraph into a clear string for the LLM
    analysis_details = json.dumps(structured_results, indent=2)

    prompt = f"""
You are an expert C programming tutor and code examiner.
A student has submitted the C code below. The code was compiled, tested, and analyzed 
by an automatic grader (LangGraph) and the raw, structured results are provided.
Your job is to synthesize all this information into a single, comprehensive,
and highly professional evaluation for the student.

Your report MUST include:
1.  **Overall Summary and Final Score:** Mention the final score ({structured_results.get('final_score', 'N/A')}%) and a brief overall assessment.
2.  **Detailed Analysis (Based on Sections):** Go through the key findings from the 'sections' in the structured results (Compilation, Test Cases, Static Analysis, Performance). Explain what happened in each section clearly.
3.  **Alternative Code / Suggestions:** Provide concrete, corrected code snippets to fix the most critical issues, especially if the code failed to compile or had low test scores. Focus on correctness and style.
4.  **Conclusion:** A concluding paragraph on the code's next steps and areas for improvement.

---
### Original C Code
```c
{c_code}
```
---
### Structured Grader Results (Raw Data)
```json
{analysis_details}
```
---

Now, please generate the final, consolidated report for the student.
"""
    report_text = call_gemini(prompt)
    return report_text or "The final report generation failed."


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
