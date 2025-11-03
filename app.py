"""
App.py - Streamlit UI

This file is the front-end for the autograder. It accepts C code (paste/upload),
optional test cases (one per line, in format input::expected_output), runs the
grading pipeline and displays results.

WARNING: The grader pipeline compiles and runs submitted C code on the host by default.
Do NOT run this Streamlit app on an unprotected host with untrusted users. Use Docker or other sandbox.
"""

import streamlit as st
from typing import List
import logging
import io
import textwrap

# Import the pipeline modules (they use logging, not Streamlit)
import grader_langgraph as grader
import llm_agents

# Configure logging to show in console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="C Autograder", layout="wide")

st.title("C Autograder (Safe Mode Warning)")
st.markdown(
    """
    **Important:** This demo compiles and runs submitted C code using `gcc` and subprocess.
    For local testing only. **Do not** deploy this on a production host without proper sandboxing.
    """
)

with st.sidebar:
    st.header("Options")
    show_raw = st.checkbox("Show raw pipeline output", value=False)
    use_llm_for_tests = st.checkbox("Auto-generate tests using LLM (if available)", value=False)
    generate_llm_report = st.checkbox("Generate detailed LLM report (if available)", value=True)
    max_tests = st.number_input("Max auto testcases", min_value=1, max_value=12, value=6)

st.header("Submit C source code")
uploaded = st.file_uploader("Upload C file (.c) or paste code below", type=["c", "txt"])
code_text = ""
if uploaded is not None:
    try:
        code_bytes = uploaded.read()
        code_text = code_bytes.decode("utf-8")
    except Exception:
        # fallback
        code_text = str(uploaded.getvalue())

code_text_area = st.text_area("C source code", value=code_text, height=300)

st.markdown("---")
st.header("Testcases (one per line, format: input::expected_output)")
tests_text = st.text_area("Optional: provide tests (leave empty to auto-generate)", value="", height=150)
run_btn = st.button("Run Autograder")

def parse_tests_from_text(t: str) -> List[str]:
    out = []
    for line in t.splitlines():
        s = line.strip()
        if s:
            out.append(s)
    return out

if run_btn:
    code_to_grade = code_text_area.strip()
    if not code_to_grade:
        st.error("Please provide C source code either by uploading a .c file or pasting in the textbox.")
    else:
        st.info("Starting grading pipeline...")
        # Prepare tests: either user-provided or LLM-generated (if available)
        user_tests = parse_tests_from_text(tests_text or "")
        if not user_tests and use_llm_for_tests:
            st.info("Requesting testcases from LLM...")
            generated = llm_agents.generate_test_cases(code_to_grade)
            if generated:
                # respect max_tests setting
                generated = generated[:max_tests]
                st.success(f"LLM returned {len(generated)} testcases.")
                user_tests = generated
            else:
                st.warning("LLM could not generate testcases. Please provide tests manually.")
        # Final tests list
        tests_list = user_tests

        # Run pipeline
        try:
            # llm_reporter: pass llm_agents.generate_detailed_report only if requested
            llm_reporter = llm_agents.generate_detailed_report if generate_llm_report else None
            results = grader.run_grader_pipeline(code_to_grade, tests=tests_list, llm_reporter=llm_reporter)
            # Show results
if show_raw:
    st.subheader("Raw pipeline output")
    st.json(results)

st.subheader("Summary")

if results.get("error"):
    st.error(f"Pipeline error: {results.get('error')}")
else:
    st.metric("Final Score", f"{results.get('final_score', 0)} / 100")

    st.markdown("### Detailed Report")
    report_text = results.get("report") or "No report generated."
    st.markdown(report_text.replace("\n", "<br/>"), unsafe_allow_html=True)

    # --- Create human-readable PDF report ---
    pdf_bytes = grader.create_pdf_report(report_text, results)
    st.download_button(
        label="📄 Download Full Report (PDF)",
        data=pdf_bytes,
        file_name="C_Grading_Report.pdf",
        mime="application/pdf",
    )

    st.success("✅ Evaluation complete. Temporary binaries cleaned up automatically.")

        except Exception as e:
            st.error(f"Grading pipeline failed: {e}")
            results = {"error": str(e)}

        # Show results
        if show_raw:
            st.subheader("Raw pipeline output")
            st.json(results)

        st.subheader("Summary")
        if results.get("error"):
            st.error(f"Pipeline error: {results.get('error')}")
        else:
            final_score = results.get("final_score")
            if final_score is not None:
                st.metric("Final Score", f"{final_score} / 100")
            compile_info = results.get("compile") or {}
            if compile_info.get("status") == "success":
                st.success("Compilation: success")
            else:
                st.error("Compilation: failed")
                st.code(compile_info.get("stderr", "No compiler stderr available."))

            st.markdown("### Static analysis")
            st.write(results.get("static"))

            st.markdown("### Tests")
            test_info = results.get("test") or {}
            st.write(test_info)
            if test_info.get("results"):
                with st.expander("Detailed test results"):
                    for idx, r in enumerate(test_info["results"]):
                        st.write(f"Test #{idx+1}")
                        st.write(r)

            st.markdown("### Performance")
            st.write(results.get("perf"))

            st.markdown("### Detailed report")
            report_text = results.get("report") or "No report generated."
            st.text_area("Report", value=report_text, height=300)

            # Offer download of report as text file
            report_bytes = report_text.encode("utf-8")
            st.download_button("Download report (.txt)", data=report_bytes, file_name="grading_report.txt", mime="text/plain")

            # Cleanup: inform user where binary (if any) is left
            compile_out = results.get("compile") or {}
            binary_path = compile_out.get("binary_path")
            if binary_path:
                st.warning("A compiled binary exists on the server at: %s" % binary_path)
                st.markdown(
                    "⚠️ For safety, manually delete temporary compilation directories on the host or add cleanup logic in the pipeline."
                )

st.markdown("---")
st.caption("This is a development/demo autograder. For production use, implement robust sandboxing and monitoring.")

