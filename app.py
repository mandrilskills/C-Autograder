# app.py
import streamlit as st
import json
import logging
from io import BytesIO

import llm_agents
import grader_langgraph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="MandrilSkills Hybrid C Autograder", layout="wide")

st.title("🤖 MandrilSkills Hybrid C Autograder")
st.caption("Groq for test-case generation • Gemini for report • GCC + Cppcheck for evaluation")

tab1, tab2, tab3, tab4 = st.tabs(["🧾 Code", "🧪 Test Cases", "📊 Evaluation", "⚙️ Diagnostics"])

if "code_text" not in st.session_state:
    st.session_state.code_text = ""
if "tests" not in st.session_state:
    st.session_state.tests = []
if "last_eval" not in st.session_state:
    st.session_state.last_eval = None

# ------------------ TAB 1 ------------------
with tab1:
    st.subheader("Upload or Paste C Program")

    uploaded = st.file_uploader("Upload a .c file", type=["c"])
    code_area = st.text_area("Or paste C code here:", st.session_state.code_text, height=300)

    if uploaded:
        st.session_state.code_text = uploaded.read().decode("utf-8")
    elif code_area:
        st.session_state.code_text = code_area.strip()

    if st.button("💡 Generate Test Cases (Groq)"):
        if not st.session_state.code_text:
            st.warning("Please provide C code first.")
        else:
            with st.spinner("Generating test cases via Groq..."):
                res = llm_agents.generate_test_cases_with_logging(st.session_state.code_text)
                st.session_state.tests = res["tests"]
                st.session_state.test_reason = res["reason"]

            st.success(f"Status: {res['status']} — {res['reason']}")
            st.text_area("Generated Test Cases (Editable)", "\n".join(st.session_state.tests), height=180)

# ------------------ TAB 2 ------------------
with tab2:
    st.subheader("View / Edit Test Cases")
    test_input = st.text_area(
        "Edit or add test cases (format: input::expected):",
        value="\n".join(st.session_state.tests) if st.session_state.tests else "",
        height=200,
    )

    if st.button("💾 Save Test Cases"):
        st.session_state.tests = [ln.strip() for ln in test_input.splitlines() if ln.strip()]
        st.success("✅ Test cases saved successfully.")

# ------------------ TAB 3 ------------------
with tab3:
    st.subheader("Run Evaluation")

    if st.button("▶️ Run Evaluation"):
        if not st.session_state.code_text:
            st.warning("Please provide code first.")
        elif not st.session_state.tests:
            st.warning("Please generate or provide test cases.")
        else:
            with st.spinner("Running full evaluation pipeline..."):
                eval_results = grader_langgraph.run_grader_pipeline(
                    st.session_state.code_text,
                    st.session_state.tests,
                    llm_reporter=llm_agents.generate_llm_report,
                    per_test_timeout=3,
                )
                st.session_state.last_eval = eval_results

            st.success(f"✅ Evaluation Complete — Score: {eval_results['final_score']} / 100")
            st.divider()

            st.markdown("### Compilation")
            st.json(eval_results["compile"])

            st.markdown("### Static Analysis")
            st.json(eval_results["static"])

            st.markdown("### Functional Tests")
            for t in eval_results["test"]["results"]:
                st.markdown(
                    f"**Input:** `{t['input']}`  \n"
                    f"**Expected:** `{t['expected']}`  \n"
                    f"**Actual:** `{t['actual']}`  \n"
                    f"✅ Success: `{t['success']}` | 💬 {t['comment']}"
                )
                st.divider()

            st.markdown("### Performance")
            st.json(eval_results["perf"])

            st.markdown("### Gemini Report")
            st.text_area("LLM Report", eval_results["report"], height=200)

            pdf_bytes = eval_results.get("pdf_bytes", b"")
            if pdf_bytes:
                st.download_button(
                    "📥 Download PDF Report",
                    data=pdf_bytes,
                    file_name="C_Autograder_Report.pdf",
                    mime="application/pdf",
                )

# ------------------ TAB 4 ------------------
with tab4:
    st.subheader("Diagnostics")
    diag = grader_langgraph.run_diagnostics()
    st.json(diag)

    if st.button("🔍 Test Gemini API"):
        st.info(llm_agents.test_gemini_connection())

    st.markdown("---")
    st.caption("Groq for test generation | Gemini for detailed reporting | gcc & cppcheck for evaluation")
