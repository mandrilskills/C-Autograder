# app.py
import streamlit as st
import os
import json
from llm_agents import generate_test_cases_with_logging, generate_llm_report, test_gemini_connection

st.set_page_config(page_title="C Autograder – Groq OSS 20B + Gemini 2.5 Flash", layout="wide")

st.title("🧠 C Autograder – Groq OSS 20B + Gemini 2.5 Flash")
st.caption("LLM Providers: Groq (openai/gpt-oss-20b) for test cases · Gemini 2.5 Flash for reports")

# ---------------- Diagnostics ----------------
st.subheader("Environment Diagnostics")
env_info = {
    "gcc": os.system("which gcc > /dev/null") == 0,
    "cppcheck": os.system("which cppcheck > /dev/null") == 0,
    "groq_api": bool(os.getenv("GROQ_API_KEY")),
    "genai_api": bool(os.getenv("GENAI_API_KEY")),
    "details": {
        "which_gcc": os.popen("which gcc").read().strip(),
        "which_cppcheck": os.popen("which cppcheck").read().strip(),
        "env_GROQ_API_KEY": bool(os.getenv("GROQ_API_KEY")),
        "env_GENAI_API_KEY": bool(os.getenv("GENAI_API_KEY")),
    },
}
st.json(env_info)

with st.expander("🔗 Test Gemini 2.5 Flash Connection"):
    st.text(test_gemini_connection())

# ---------------- Code Input ----------------
st.header("1️⃣ Upload or Paste C Code")
upload = st.file_uploader("Upload .c file", type=["c"])
code_text = upload.read().decode("utf-8") if upload else st.text_area("Paste C code here:", height=300)

# ---------------- Test Case Generation ----------------
if st.button("🚀 Generate Test Cases (via Groq OSS 20B)"):
    if not code_text.strip():
        st.error("Please enter a valid C program first.")
    else:
        with st.spinner("Generating test cases via Groq (openai/gpt-oss-20b)..."):
            res = generate_test_cases_with_logging(code_text)
        st.success(f"Status: {res['status']} — {res['reason']}")
        test_cases = "\n".join(res["tests"])
        st.session_state["tests"] = test_cases
        st.text_area("Generated Test Cases (Editable)", test_cases, height=200)

# ---------------- Evaluation ----------------
st.header("2️⃣ Run Evaluation and Generate Report")
if st.button("🏁 Run Evaluation"):
    if not code_text.strip():
        st.warning("Please provide C code first.")
    else:
        from grader_langgraph import run_grader_pipeline
        with st.spinner("Running evaluation..."):
            eval_data = run_grader_pipeline(
                code_text,
                st.session_state.get("tests", "").splitlines(),
                llm_reporter=generate_llm_report,
            )
        st.success(f"✅ Evaluation completed — Score: {eval_data.get('final_score', 'NA')}")
        st.json(eval_data)
        st.text_area("📘 Gemini 2.5 Flash Report", eval_data["report"], height=300)
