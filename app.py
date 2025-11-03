# app.py
"""
Streamlit App for C Autograder (Flexible + Timeout Control)
- Accepts .c file or pasted code
- Optionally generates test cases using Gemini (LLM)
- Allows user to review / edit test cases (any format)
- Executes grader pipeline with configurable timeout per test
- Shows compilation, static analysis, test results, performance, and LLM-based report
"""

import streamlit as st
import grader_langgraph as grader
import llm_agents
import logging
import json

logger = logging.getLogger(__name__)

# Page setup
st.set_page_config(page_title="C Autograder", layout="wide")
st.title("🧠 C Autograder (Agentic Evaluation System)")

st.markdown("""
### 📘 Instructions
1. Upload or paste your **C code** below.  
2. Either **enter test cases manually** (any format) or **generate automatically** using Gemini.  
3. Adjust per-test **timeout** slider (default: 5 seconds).  
4. Click **Run Evaluation** to start grading.
""")

# Upload or paste code
uploaded = st.file_uploader("Upload `.c` file", type=["c", "txt"])
code_text = uploaded.read().decode("utf-8") if uploaded else ""

code_text_area = st.text_area("Paste or edit your C code here:", code_text, height=300)

# Sidebar / Options
st.sidebar.header("⚙️ Options")
use_llm_for_tests = st.sidebar.checkbox("Use LLM to generate test cases", value=False)
generate_llm_report = st.sidebar.checkbox("Generate detailed report using LLM", value=True)
timeout_val = st.sidebar.slider("⏱️ Per-test timeout (seconds)", min_value=1, max_value=10, value=5)

# Step 1: Generate test cases using LLM if requested
if st.button("🤖 Generate Test Cases via LLM") and code_text_area.strip():
    with st.spinner("Generating test cases using Gemini (LLM)..."):
        generated_cases = llm_agents.generate_test_cases(code_text_area)
        if generated_cases:
            st.session_state["auto_tests"] = "\n".join(generated_cases)
            st.success(f"✅ Generated {len(generated_cases)} test cases successfully.")
        else:
            st.warning("⚠️ Gemini could not generate test cases. Please add them manually.")

# Step 2: Show test case input area
default_tests = st.session_state.get("auto_tests", "")
tests_text = st.text_area(
    "🧪 Review / Edit Test Cases (JSON, plain input, or 'input::output' format accepted):",
    value=default_tests,
    height=200,
)

# Step 3: Run evaluation pipeline
if st.button("🚀 Run Evaluation"):
    code_to_grade = code_text_area.strip()
    if not code_to_grade:
        st.error("Please provide your C source code.")
    else:
        st.info("Running agent-based evaluation using gcc, cppcheck, and runtime execution...")

        try:
            # Call grader pipeline
            test_block = tests_text.strip()
            llm_reporter = llm_agents.generate_detailed_report if generate_llm_report else None

            # Run grader with timeout control
            results = grader.run_grader_pipeline(
                code_to_grade,
                test_block,
                llm_reporter=llm_reporter,
            )

            # --- Display evaluation summary ---
            st.subheader("📊 Evaluation Summary")
            st.metric("Final Score", f"{results.get('final_score', 0)} / 100")

            st.markdown("### 🧪 Test Case Results")
            if not results.get("test", {}).get("results"):
                st.warning("No test cases evaluated.")
            else:
                for i, t in enumerate(results["test"]["results"], start=1):
                    status = "✅ PASS" if t["success"] else "❌ FAIL"
                    st.markdown(
                        f"**Test {i}:** `{t['input']}` → expected `{t.get('expected', '(N/A)')}` "
                        f"| got `{t['actual']}` | {status}<br/>"
                        f"🕒 Comment: *{t.get('comment', 'OK')}*",
                        unsafe_allow_html=True,
                    )

            st.markdown("### ⚙️ Compilation Output")
            stderr = results.get("compile", {}).get("stderr", "")
            st.text(stderr if stderr else "Compiled successfully without errors.")

            st.markdown("### 🧰 Static Analysis")
            st.json(results.get("static", {}))

            st.markdown("### 🚀 Performance")
            st.json(results.get("perf", {}))

            st.markdown("### 🧾 LLM-Generated Report")
            report_text = results.get("report")
            if report_text:
                st.markdown(report_text.replace("\n", "<br/>"), unsafe_allow_html=True)
            else:
                st.warning("No LLM report generated (fallback used).")

            if results.get("pdf_bytes"):
                st.download_button(
                    "📄 Download Full Report (PDF)",
                    data=results["pdf_bytes"],
                    file_name="C_Autograder_Report.pdf",
                    mime="application/pdf",
                )

            st.success("✅ Evaluation completed successfully.")

        except Exception as e:
            st.error(f"Evaluation failed: {e}")
            logger.exception("Grader pipeline exception")
