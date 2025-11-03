# app.py (Flexible Test Format + Proper Routing)
import streamlit as st
import grader_langgraph as grader
import llm_agents
import logging
import json

logger = logging.getLogger(__name__)

st.set_page_config(page_title="C Autograder", layout="wide")
st.title("C Autograder (Flexible Test Evaluation System)")

st.markdown("""
### Upload or Paste Your C Code
You can either provide test cases manually (in any format) or let Gemini auto-generate them.
After generation, you can review or edit the cases before running the evaluation.
""")

uploaded = st.file_uploader("Upload `.c` file", type=["c", "txt"])
code_text = uploaded.read().decode("utf-8") if uploaded else ""

code_text_area = st.text_area("Paste or edit your C code:", code_text, height=300)

# Options
use_llm_for_tests = st.checkbox("Generate test cases using LLM (Gemini 2.5 Flash)", value=False)
generate_llm_report = st.checkbox("Generate detailed report using LLM", value=True)

# Step 1: Generate test cases if requested
if st.button("Generate Test Cases via LLM") and code_text_area.strip():
    with st.spinner("Contacting Gemini to generate test cases..."):
        generated = llm_agents.generate_test_cases(code_text_area)
        if generated:
            st.session_state["auto_tests"] = "\n".join(generated)
            st.success(f"Generated {len(generated)} test cases successfully.")
        else:
            st.warning("Gemini failed to produce test cases. Please add them manually.")

# Step 2: Display editable test area
default_tests = st.session_state.get("auto_tests", "")
tests_text = st.text_area(
    "Review/Edit Test Cases (any format accepted: plain input, JSON, or input::output)",
    value=default_tests,
    height=200,
)

# Step 3: Run evaluation
if st.button("Run Evaluation"):
    code_to_grade = code_text_area.strip()
    if not code_to_grade:
        st.error("Please enter valid C source code.")
    else:
        st.info("Running agent-based evaluation using gcc, cppcheck, and runtime tests...")

        try:
            test_block = tests_text.strip()
            llm_reporter = llm_agents.generate_detailed_report if generate_llm_report else None

            # Call grader pipeline (auto-detects test structure)
            results = grader.run_grader_pipeline(code_to_grade, test_block, llm_reporter=llm_reporter)

            # --- Display results ---
            st.metric("Final Score", f"{results.get('final_score', 0)} / 100")

            st.markdown("### 🧪 Test Case Results")
            for i, t in enumerate(results.get("test", {}).get("results", []), start=1):
                status = "✅ PASS" if t["success"] else "❌ FAIL"
                st.write(f"**Test {i}:** input={t['input']} | expected={t.get('expected', '(N/A)')} | got={t['actual']} | {status}")

            st.markdown("### ⚙️ Compilation Output")
            st.text(results.get("compile", {}).get("stderr", "") or "Compiled successfully.")

            st.markdown("### 🧰 Static Analysis")
            st.json(results.get("static", {}))

            st.markdown("### 🚀 Performance")
            st.json(results.get("perf", {}))

            st.markdown("### 🧾 LLM-Generated Report")
            if results.get("report"):
                st.markdown(results["report"].replace("\n", "<br/>"), unsafe_allow_html=True)
            else:
                st.warning("No LLM report generated.")

            if results.get("pdf_bytes"):
                st.download_button(
                    "📄 Download Full Report (PDF)",
                    data=results["pdf_bytes"],
                    file_name="C_Autograder_Report.pdf",
                    mime="application/pdf",
                )

        except Exception as e:
            st.error(f"Evaluation failed: {e}")
            logger.exception("Evaluation Error")
