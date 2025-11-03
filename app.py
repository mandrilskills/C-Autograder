# app.py
import streamlit as st
import logging
import json
import grader_langgraph as grader
import llm_agents

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="C Autograder — Debuggable", layout="wide")
st.title("C Autograder — Debug & Run")

st.markdown("""
**Quick checklist before running**
- Ensure `packages.txt` (gcc, cppcheck) is installed in your environment (Streamlit Cloud requires a restart after change).
- Set `GENAI_API_KEY` in environment / Streamlit Secrets.
""")

# Upload / paste area
uploaded = st.file_uploader("Upload `.c` file", type=["c", "txt"])
code_default = uploaded.read().decode("utf-8") if uploaded else ""
code_text = st.text_area("C source code", value=code_default, height=300)

# Options
st.sidebar.header("Options")
use_llm_for_tests = st.sidebar.checkbox("Generate tests with LLM", value=True)
generate_llm_report = st.sidebar.checkbox("Generate LLM report", value=True)
timeout_val = st.sidebar.slider("Per-test timeout (s)", 1, 15, 5)

# Diagnostics panel
st.header("Diagnostics")
if st.button("Run Environment Diagnostics"):
    diag = grader.run_diagnostics()
    st.subheader("Diagnostics result")
    st.json(diag)

st.markdown("---")
st.header("Test-cases")
if st.button("Generate test-cases (LLM)"):
    if not code_text.strip():
        st.warning("Provide code first.")
    else:
        with st.spinner("Generating test cases using LLM..."):
            gen_result = llm_agents.generate_test_cases_with_logging(code_text)
            st.subheader("LLM test-generation result")
            st.write("status:", gen_result.get("status"))
            if gen_result.get("reason"):
                st.info(gen_result["reason"])
            tests_text = "\n".join(gen_result.get("tests", []))
            st.text_area("Generated testcases (editable)", value=tests_text, height=200, key="generated_tests")

# Display editable tests area
tests_text_area = st.text_area("Manual / Edited testcases (any format accepted)", value=st.session_state.get("generated_tests", ""), height=200)

# Run Evaluation
if st.button("Run Evaluation"):
    if not code_text.strip():
        st.error("Please provide code.")
    else:
        st.info("Starting grading pipeline...")
        # pass raw test block and timeout
        results = grader.run_grader_pipeline(code_text, tests_text_area.strip(), llm_reporter=(llm_agents.generate_detailed_report if generate_llm_report else None), per_test_timeout=timeout_val)
        st.subheader("Evaluation Summary")
        st.metric("Score", f"{results.get('final_score',0)} / 100")
        st.subheader("Compile info")
        st.write(results.get("compile", {}))
        st.subheader("Static analysis")
        st.write(results.get("static", {}))
        st.subheader("Test results")
        for i, r in enumerate(results.get("test", {}).get("results", []), start=1):
            st.markdown(f"**Test {i}** — input: `{r.get('input')}` — expected: `{r.get('expected','(N/A)')}` — actual: `{r.get('actual')}`")
            st.write("success:", r.get("success"), "| comment:", r.get("comment"), "| stderr:", r.get("stderr"))
        st.subheader("Performance")
        st.write(results.get("perf", {}))
        st.subheader("LLM report (if generated)")
        st.write(results.get("report") or "(no report)")
        if results.get("pdf_bytes"):
            st.download_button("Download PDF report", data=results["pdf_bytes"], file_name="report.pdf", mime="application/pdf")
