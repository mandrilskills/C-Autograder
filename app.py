# app.py (Updated Test Case Handling)
import streamlit as st
import grader_langgraph as grader
import llm_agents
import logging

logger = logging.getLogger(__name__)

st.set_page_config(page_title="C Autograder", layout="wide")
st.title("C Autograder (Agentic System)")

st.markdown("""
### Upload or paste your C code
You can manually provide test cases or let Gemini (LLM) auto-generate them.
After generation, you can review or edit the cases before evaluation.
""")

uploaded = st.file_uploader("Upload `.c` file", type=["c", "txt"])
code_text = uploaded.read().decode("utf-8") if uploaded else ""

code_text_area = st.text_area("Paste or edit your C code here:", code_text, height=300)

# Options
use_llm_for_tests = st.checkbox("Auto-generate test cases using LLM (Gemini 2.5 Flash)", value=False)
generate_llm_report = st.checkbox("Generate detailed LLM report after evaluation", value=True)

# --- Step 1: Generate test cases ---
if st.button("Generate Test Cases via LLM") and code_text_area.strip():
    with st.spinner("Generating test cases using Gemini..."):
        generated_tests = llm_agents.generate_test_cases(code_text_area)
        if generated_tests:
            st.session_state["auto_tests"] = "\n".join(generated_tests)
            st.success(f"✅ {len(generated_tests)} test cases generated successfully.")
        else:
            st.warning("⚠️ Gemini could not generate test cases. Please enter manually.")

# --- Step 2: Let user review / edit test cases ---
default_tests = st.session_state.get("auto_tests", "")
tests_text = st.text_area(
    "Review / edit test cases (one per line in format input::expected_output):",
    value=default_tests,
    height=160,
)

# --- Step 3: Run grading pipeline ---
if st.button("Run Evaluation"):
    code_to_grade = code_text_area.strip()
    if not code_to_grade:
        st.error("Please provide your C source code.")
    else:
        test_cases = [t.strip() for t in tests_text.splitlines() if "::" in t]
        if not test_cases:
            st.warning("No valid test cases found. Compilation and static analysis will still be performed.")

        st.info("Running grader agents (gcc, cppcheck, execution)...")
        try:
            llm_reporter = llm_agents.generate_detailed_report if generate_llm_report else None
            results = grader.run_grader_pipeline(code_to_grade, test_cases, llm_reporter=llm_reporter)

            # --- Display Evaluation Summary ---
            st.subheader("Evaluation Summary")
            st.metric("Final Score", f"{results.get('final_score', 0)} / 100")

            st.markdown("### 🧪 Test Case Results")
            for i, t in enumerate(results.get("test", {}).get("results", []), start=1):
                status = "✅ PASS" if t["success"] else "❌ FAIL"
                st.write(f"**Test {i}:** `{t['input']}` → expected `{t['expected']}` | got `{t['actual']}` | {status}")

            st.markdown("### 🧰 Static Analysis")
            st.json(results.get("static", {}))

            st.markdown("### ⚙️ Compilation Output")
            st.text(results.get("compile", {}).get("stderr", "") or "Compiled successfully.")

            st.markdown("### 🚀 Performance")
            st.json(results.get("perf", {}))

            if results.get("report"):
                st.markdown("### 🧾 LLM-Generated Detailed Report")
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
            st.error(f"Pipeline failed: {e}")
            logger.exception("Evaluation error")
