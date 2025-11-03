# app.py
"""
Streamlit UI for the C Autograder

- Upload or paste a C program.
- Optionally auto-generate test cases with an LLM.
- Run compilation, static analysis (cppcheck), tests, and performance using grader agents.
- Orchestrate results into JSON, then ask Gemini (LLM) to create a detailed textual report
  based on that JSON (LLM is only used for writing the report — not for evaluation).
- Provide a downloadable PDF containing the LLM-written report and grader JSON summary.
"""

import streamlit as st
from typing import List
import logging

import grader_langgraph as grader
import llm_agents

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="C Autograder", layout="wide")
st.title("C Autograder (Agentic System)")

st.markdown(
    """
**Security warning:** this demo compiles & runs untrusted C code locally.
For production, run each submission inside a secure sandbox (Docker, container runtime, VM).
"""
)

# Sidebar options
with st.sidebar:
    st.header("Options")
    show_raw = st.checkbox("Show raw evaluation JSON", value=False)
    use_llm_for_tests = st.checkbox("Auto-generate test cases using LLM", value=False)
    generate_llm_report = st.checkbox("Use LLM to write final report (recommended)", value=True)
    max_tests = st.number_input("Max auto test cases", min_value=1, max_value=20, value=6)

# Upload or paste code
st.header("Submit C Source Code")
uploaded = st.file_uploader("Upload `.c` file or paste your code", type=["c", "txt"])
code_text = ""
if uploaded is not None:
    try:
        code_text = uploaded.read().decode("utf-8")
    except Exception:
        code_text = str(uploaded.getvalue())

code_text_area = st.text_area("Paste or edit your C code here", value=code_text, height=300)

st.markdown("---")
st.header("Test cases (one per line) — format: input::expected_output")
tests_text = st.text_area(
    "Provide test cases manually (leave blank to auto-generate via LLM if option enabled).",
    value="",
    height=140,
)

run_btn = st.button("Run Autograder")

def parse_tests_from_text(t: str) -> List[str]:
    return [line.strip() for line in t.splitlines() if line.strip()]

if run_btn:
    code_to_grade = code_text_area.strip()
    if not code_to_grade:
        st.error("Please provide C source code to evaluate.")
    else:
        st.info("Starting grading pipeline...")

        # 1) Prepare tests
        tests_list = parse_tests_from_text(tests_text)
        if not tests_list and use_llm_for_tests:
            st.info("Generating test cases using LLM...")
            generated = llm_agents.generate_test_cases(code_to_grade)
            if generated:
                tests_list = generated[:max_tests]
                st.success(f"Generated {len(tests_list)} test cases using LLM.")
            else:
                st.warning("LLM could not produce test cases. Please enter them manually.")

        if not tests_list:
            st.warning("No test cases provided. The grader will still run compilation & static analysis.")

        # 2) Run grader pipeline (LLM reporter passed but reported LLM will only produce report text)
        try:
            llm_reporter = llm_agents.generate_detailed_report if generate_llm_report else None
            results = grader.run_grader_pipeline(code_to_grade, tests=tests_list, llm_reporter=llm_reporter)

            if show_raw:
                st.subheader("Raw evaluation JSON")
                st.json(results)

            st.subheader("Evaluation Summary")
            if results.get("error"):
                st.error(f"Pipeline error: {results.get('error')}")
            else:
                st.metric("Final Score", f"{results.get('final_score', 0)} / 100")
                st.markdown("### LLM-written Report (if available)")
                report_text = results.get("report") or "No report generated."
                # report_text may contain newlines; display as markdown
                st.markdown(report_text.replace("\n", "<br/>"), unsafe_allow_html=True)

                # Downloadable PDF
                pdf_bytes = results.get("pdf_bytes")
                if pdf_bytes:
                    st.download_button(
                        "Download Full Report (PDF)",
                        data=pdf_bytes,
                        file_name="C_Grading_Report.pdf",
                        mime="application/pdf",
                    )

                st.markdown("### Compilation output")
                st.write(results.get("compile", {}))

                st.markdown("### Static analysis (cppcheck / heuristics)")
                st.write(results.get("static", {}))

                st.markdown("### Test case results")
                st.write(results.get("test", {}))
                if results.get("test", {}).get("results"):
                    with st.expander("Detailed test results"):
                        for idx, t in enumerate(results["test"]["results"], start=1):
                            st.write(f"Test #{idx}:")
                            st.json(t)

                st.markdown("### Performance")
                st.write(results.get("perf", {}))

                st.success("Evaluation completed. Temporary files cleaned up.")

        except Exception as e:
            st.error(f"Grading pipeline failed: {e}")
            logger.exception("Grader pipeline exception")

st.caption("© 2025 C Autograder — Use sandboxing for production.")
