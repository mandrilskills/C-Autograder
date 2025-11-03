# app.py
import streamlit as st
import json
import logging
from io import BytesIO

import llm_agents
import grader_langgraph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="MandrilSkills C Autograder", layout="wide")

# --------------------------- UI ---------------------------
st.title("🧠 MandrilSkills C Autograder")
st.caption("Evaluate your C programs using GCC, Cppcheck & Gemini 2.5 / 1.5 models")

# --- Tabs ---
tab1, tab2, tab3, tab4 = st.tabs(["🏁 Upload / Code", "🧪 Test Cases", "📊 Evaluation", "⚙️ Diagnostics"])

# --------------------------- Globals ---------------------------
if "code_text" not in st.session_state:
    st.session_state.code_text = ""
if "tests" not in st.session_state:
    st.session_state.tests = []
if "last_eval" not in st.session_state:
    st.session_state.last_eval = None
if "test_reason" not in st.session_state:
    st.session_state.test_reason = ""

# ============================================================
# TAB 1: CODE INPUT
# ============================================================
with tab1:
    st.subheader("Upload or Paste Your C Code")

    uploaded = st.file_uploader("Upload a .c file", type=["c"])
    code_area = st.text_area(
        "Or paste your C code here:",
        st.session_state.code_text,
        height=300,
        placeholder="Paste your C source code...",
    )

    if uploaded:
        st.session_state.code_text = uploaded.read().decode("utf-8")
    elif code_area:
        st.session_state.code_text = code_area

    st.session_state.code_text = st.session_state.code_text.strip()

    if st.button("💡 Generate Test Cases using Gemini"):
        if not st.session_state.code_text:
            st.warning("Please paste or upload your C code first.")
        else:
            with st.spinner("Contacting Gemini for test-case generation..."):
                res = llm_agents.generate_test_cases_with_logging(st.session_state.code_text)
                st.session_state.tests = res["tests"]
                st.session_state.test_reason = res["reason"]

            st.success(f"Status: {res['status']} — {res['reason']}")
            st.text_area("Generated Test Cases (Editable)", "\n".join(st.session_state.tests), height=180)

# ============================================================
# TAB 2: TEST CASES
# ============================================================
with tab2:
    st.subheader("View / Edit Test Cases")
    st.write("💡 You can manually edit the test cases if needed. Format: `input::expected_output`")

    test_input = st.text_area(
        "Test Cases (any format accepted):",
        value="\n".join(st.session_state.tests) if st.session_state.tests else "",
        height=200,
    )

    if st.button("💾 Save Test Cases"):
        st.session_state.tests = [ln.strip() for ln in test_input.splitlines() if ln.strip()]
        st.success("✅ Test cases updated.")

# ============================================================
# TAB 3: EVALUATION
# ============================================================
with tab3:
    st.subheader("Run Evaluation")

    if st.button("▶️ Run Evaluation"):
        if not st.session_state.code_text:
            st.warning("Please provide a C program first.")
        elif not st.session_state.tests:
            st.warning("Please generate or enter test cases before evaluation.")
        else:
            with st.spinner("Running full evaluation pipeline..."):
                eval_results = grader_langgraph.run_grader_pipeline(
                    st.session_state.code_text,
                    st.session_state.tests,
                    llm_reporter=llm_agents.generate_llm_report,
                    per_test_timeout=3,
                )
                st.session_state.last_eval = eval_results

            st.success("✅ Evaluation Completed Successfully")
            st.markdown(f"### Final Score: `{eval_results['final_score']}` / 100")

            # Display results
            st.markdown("#### 🧩 Compilation")
            st.json(eval_results["compile"])

            st.markdown("#### 🧠 Static Analysis")
            st.json(eval_results["static"])

            st.markdown("#### 🧪 Test Case Results")
            for t in eval_results["test"]["results"]:
                st.markdown(
                    f"**Input:** `{t['input']}`  \n"
                    f"**Expected:** `{t['expected']}`  \n"
                    f"**Actual:** `{t['actual']}`  \n"
                    f"✅ Success: `{t['success']}` | 💬 Comment: {t['comment']}"
                )
                st.divider()

            st.markdown("#### ⚙️ Performance")
            st.json(eval_results["perf"])

            st.markdown("#### 🧾 LLM Report")
            st.text_area("C Code Evaluation Report", eval_results["report"] or "No report generated.", height=200)

            # Download PDF
            pdf_bytes = eval_results.get("pdf_bytes", b"")
            if pdf_bytes:
                st.download_button(
                    label="📥 Download Detailed PDF Report",
                    data=pdf_bytes,
                    file_name="C_Autograder_Report.pdf",
                    mime="application/pdf",
                )

# ============================================================
# TAB 4: DIAGNOSTICS
# ============================================================
with tab4:
    st.subheader("Environment Diagnostics")
    diag = grader_langgraph.run_diagnostics()
    st.json(diag)

    if st.button("🔍 Test Gemini API connection"):
        with st.spinner("Testing Gemini models..."):
            res = llm_agents.test_gemini_connection()
            st.info(res)

    st.markdown("---")
    st.caption("Ensure gcc, cppcheck, and GENAI_API_KEY are properly configured for best results.")
