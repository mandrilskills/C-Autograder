"""
App.py - Streamlit UI for the C Autograder

Features:
- Upload or paste a C program.
- Provide or auto-generate test cases using LLM.
- Runs compilation, static analysis, tests, and performance check.
- Generates a human-readable justified PDF report.
- Cleans up temporary binaries automatically after each run.
"""

import streamlit as st
from typing import List
import logging

# Import internal modules
import grader_langgraph as grader
import llm_agents

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Streamlit setup
st.set_page_config(page_title="C Autograder", layout="wide")
st.title("C Autograder 🧠💻")
st.caption(
    "This application evaluates C programs by compiling, testing, and analyzing performance automatically."
)
st.markdown(
    """
    ⚠️ **Security Warning:** This demo compiles and runs C code locally. 
    For production or cloud use, always sandbox student code in Docker or a similar secure environment.
    """
)

# Sidebar configuration
with st.sidebar:
    st.header("⚙️ Options")
    show_raw = st.checkbox("Show raw pipeline output", value=False)
    use_llm_for_tests = st.checkbox("Auto-generate test cases using LLM (if available)", value=False)
    generate_llm_report = st.checkbox("Use LLM to generate detailed feedback", value=True)
    max_tests = st.number_input("Max auto test cases", min_value=1, max_value=12, value=6)

# --- Upload or paste code ---
st.header("🧾 Submit Your C Source Code")
uploaded = st.file_uploader("Upload a .c file or paste your code below", type=["c", "txt"])

code_text = ""
if uploaded is not None:
    try:
        code_text = uploaded.read().decode("utf-8")
    except Exception:
        code_text = str(uploaded.getvalue())

code_text_area = st.text_area("✍️ Paste or Edit Your C Code Here", value=code_text, height=300)

# --- Test cases input ---
st.markdown("---")
st.header("🧪 Test Cases (format: input::expected_output)")
tests_text = st.text_area(
    "You can provide your own test cases. Leave blank to let the LLM auto-generate them.",
    value="",
    height=150,
)

run_btn = st.button("🚀 Run Autograder")

# Helper function
def parse_tests_from_text(t: str) -> List[str]:
    """Parse test cases from multiline input box."""
    return [line.strip() for line in t.splitlines() if line.strip()]


# --- Main grading logic ---
if run_btn:
    code_to_grade = code_text_area.strip()
    if not code_to_grade:
        st.error("Please provide C source code to evaluate.")
    else:
        st.info("🔍 Starting grading pipeline...")

        # Step 1: Prepare test cases
user_tests = parse_tests_from_text(tests_text)
if not user_tests and use_llm_for_tests:
    st.info("Requesting test cases from LLM or fallback generator...")
    generated = llm_agents.generate_test_cases(code_to_grade)
    if generated:
        user_tests = generated[:max_tests]
        st.success(f"✅ Generated {len(user_tests)} test cases automatically.")
    else:
        st.warning("❌ Could not generate test cases. Please provide them manually.")


        # Step 2: Run the grading pipeline
        try:
            llm_reporter = llm_agents.generate_detailed_report if generate_llm_report else None
            results = grader.run_grader_pipeline(code_to_grade, tests=tests_list, llm_reporter=llm_reporter)

            # Step 3: Display results
            if show_raw:
                st.subheader("🧩 Raw Pipeline Output")
                st.json(results)

            st.subheader("📊 Evaluation Summary")

            if results.get("error"):
                st.error(f"Pipeline error: {results.get('error')}")
            else:
                final_score = results.get("final_score", 0)
                st.metric("Final Score", f"{final_score} / 100")

                st.markdown("### 🧠 Detailed Feedback")
                report_text = results.get("report") or "No report generated."
                st.markdown(report_text.replace("\n", "<br/>"), unsafe_allow_html=True)

                # Generate and download PDF report
                pdf_bytes = grader.create_pdf_report(report_text, results)
                st.download_button(
                    label="📄 Download Full Report (PDF)",
                    data=pdf_bytes,
                    file_name="C_Grading_Report.pdf",
                    mime="application/pdf",
                )

                st.success("✅ Evaluation complete. Temporary binaries cleaned up automatically.")

                # Display summary sections
                st.markdown("### 🧩 Compilation Results")
                st.write(results.get("compile", {}))

                st.markdown("### 🔍 Static Analysis")
                st.write(results.get("static", {}))

                st.markdown("### 🧪 Test Case Results")
                test_info = results.get("test", {})
                st.write(test_info)

                if test_info.get("results"):
                    with st.expander("View Detailed Test Results"):
                        for idx, r in enumerate(test_info["results"]):
                            st.write(f"**Test #{idx + 1}:**")
                            st.json(r)

                st.markdown("### ⚙️ Performance Analysis")
                st.write(results.get("perf", {}))

        except Exception as e:
            st.error(f"❌ Grading pipeline failed: {e}")
            results = {"error": str(e)}

st.markdown("---")
st.caption("© 2025 C Autograder | Developed for educational evaluation of C programming assignments.")

