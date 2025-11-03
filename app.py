# app.py
import streamlit as st
import logging
import json
import grader_langgraph as grader
import llm_agents
from io import StringIO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="C Autograder — Gemini Integrated", layout="wide")
st.title("C Autograder — Gemini Enhanced Version")

st.markdown("""
### 🚀 Features
- Upload or paste a `.c` file
- Generate **test cases using Gemini (LLM)**
- Evaluate using **gcc** & **cppcheck**
- Generate **detailed LLM-based feedback report**
""")

# ---------------- Upload / Code Area ----------------
uploaded = st.file_uploader("Upload a .c file", type=["c", "txt"])
code_default = uploaded.read().decode("utf-8") if uploaded else ""
code_text = st.text_area("Paste your C code", value=code_default, height=300)

# ---------------- Sidebar Options ----------------
st.sidebar.header("Options")
use_llm_tests = st.sidebar.checkbox("Generate test cases using Gemini", value=True)
gen_llm_report = st.sidebar.checkbox("Generate detailed report using Gemini", value=True)
timeout_val = st.sidebar.slider("Execution Timeout per Test (seconds)", 1, 15, 5)

# ---------------- Diagnostics ----------------
st.subheader("Environment Diagnostics")
if st.button("Run Diagnostics"):
    diag = grader.run_diagnostics()
    st.json(diag)

# ---------------- Gemini Connectivity ----------------
st.subheader("Gemini Debug Tools")
log_stream = StringIO()
handler = logging.StreamHandler(log_stream)
logging.getLogger().addHandler(handler)

if st.button("Test Gemini Connectivity"):
    st.write("Testing Gemini API connection...")
    result = llm_agents._call_gemini("Say 'Gemini connection successful.'")
    st.write("Gemini Response:", result or "(No response)")
    st.text_area("Debug Logs", log_stream.getvalue(), height=200)

logging.getLogger().removeHandler(handler)

# ---------------- Test Case Generation ----------------
st.markdown("---")
st.subheader("Generate Test Cases")

if st.button("Generate Test Cases"):
    if not code_text.strip():
        st.warning("Please provide your C code first.")
    else:
        with st.spinner("Calling Gemini to generate test cases..."):
            gen_result = llm_agents.generate_test_cases_with_logging(code_text)
            st.success(f"Status: {gen_result.get('status')} — {gen_result.get('reason')}")
            tests_output = "\n".join(gen_result.get("tests", []))
            st.text_area("Generated Test Cases (Editable)", value=tests_output, height=200, key="generated_tests")

# ---------------- Editable Test Case Input ----------------
tests_text_area = st.text_area(
    "Enter or edit test cases (any format accepted)",
    value=st.session_state.get("generated_tests", ""),
    height=200
)

# ---------------- Evaluation ----------------
if st.button("Run Evaluation"):
    if not code_text.strip():
        st.error("Please provide your C code.")
    else:
        st.info("Starting evaluation pipeline...")
        result = grader.run_grader_pipeline(
            code_text,
            tests_text_area.strip(),
            llm_reporter=(llm_agents.generate_detailed_report if gen_llm_report else None),
            per_test_timeout=timeout_val
        )

        st.subheader("Evaluation Results")
        st.metric("Final Score", f"{result.get('final_score', 0)} / 100")
        st.write("**Compilation:**", result.get("compile"))
        st.write("**Static Analysis:**", result.get("static"))
        st.write("**Performance:**", result.get("perf"))

        st.subheader("Test Case Results")
        for i, r in enumerate(result.get("test", {}).get("results", []), start=1):
            st.markdown(f"**Test {i}:** input=`{r.get('input')}`, expected=`{r.get('expected')}`, actual=`{r.get('actual')}`")
            st.write("→ Success:", r.get("success"), "| Comment:", r.get("comment"))

        st.subheader("LLM Report")
        st.write(result.get("report") or "(LLM report not generated)")

        if result.get("pdf_bytes"):
            st.download_button(
                "Download Detailed PDF Report",
                data=result["pdf_bytes"],
                file_name="C_Autograder_Report.pdf",
                mime="application/pdf"
            )
