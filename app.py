# app.py

import streamlit as st
import os
import json
import logging
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

import llm_agents
from llm_agents import generate_test_cases_with_logging
from grader_langgraph import run_grader_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------ Page Setup ------------------
st.set_page_config(page_title="C Autograder", layout="wide", page_icon="🎓")

# ------------------ Styling ------------------
st.markdown("""
<style>
body, .main {
    background-color: #0d1117;
    color: #f8fafc;
    font-family: 'Inter', sans-serif;
}
h1, h2, h3 { color: #ffffff; font-weight: 600; }
.stButton>button {
    border-radius: 8px;
    background-color: #2563eb;
    color: white;
    font-weight: 600;
    border: none;
    transition: 0.3s;
}
.stButton>button:hover {
    background-color: #1e40af;
    transform: scale(1.02);
}
.card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.5);
    margin-bottom: 25px;
}
.report-box {
    background-color: #1b222c;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 16px;
    color: #e2e8f0;
}
.footer {
    text-align: center;
    color: #94a3b8;
    font-size: 13px;
    margin-top: 40px;
}
</style>
""", unsafe_allow_html=True)

# ------------------ Header ------------------
st.title("Welcome to C Autograder")
st.caption("A step towards better Learning Management System (LMS)")
st.markdown("---")

# ------------------ Step 1: Upload Code ------------------
with st.expander("🧱 Step 1 – Upload or Paste C Code", expanded=True):
    uploaded = st.file_uploader("📂 Upload a `.c` file", type=["c"])
    code_text = uploaded.read().decode("utf-8") if uploaded else st.text_area(
        "✏️ Paste your C code here:", height=300, placeholder="// Enter your C program here..."
    )
    if code_text:
        st.session_state["code_text"] = code_text
        st.success("✅ Code loaded successfully.")
    else:
        st.info("Please upload or paste valid C code to continue.")

# ------------------ Step 2: Generate Test Cases ------------------
with st.expander("🧪 Step 2 – Generate Test Cases (Groq OSS 20B)", expanded=False):
    code_text = st.session_state.get("code_text", "")
    if not code_text:
        st.warning("Please complete Step 1 first.")
    else:
        if st.button("🚀 Generate Test Cases"):
            with st.spinner("Generating intelligent test cases using Groq OSS 20B..."):
                res = generate_test_cases_with_logging(code_text)
            if res["status"] in ["ok", "fallback"]:
                st.session_state["tests"] = "\n".join(res["tests"])
                st.success(f"✅ {len(res['tests'])} test cases generated.")
                st.text_area("🧾 Generated Test Cases (Editable)", st.session_state["tests"], height=200)
            else:
                st.error(f"❌ Test generation failed: {res['reason']}")

# ------------------ Step 3: Evaluation ------------------
with st.expander("🏁 Step 3 – Run Evaluation and Generate Report", expanded=False):
    code_text = st.session_state.get("code_text", "")
    tests_raw = st.session_state.get("tests", "")
    if st.button("🏁 Run Evaluation"):
        if not code_text:
            st.error("Please upload or paste your C code first.")
        else:
            left, right = st.columns([0.55, 0.45])
            with left:
                with st.spinner("Running compilation, static analysis, and functional tests..."):
                    evaluation = run_grader_pipeline(
                        code_text,
                        tests_raw.splitlines(),
                        llm_reporter=llm_agents.generate_llm_report,
                    )

                compile_info = evaluation.get("compile", {})
                static_info = evaluation.get("static", {})
                test_info = evaluation.get("test", {}).get("results", [])
                perf_info = evaluation.get("perf", {})
                final_score = evaluation.get("final_score", 0)

                st.subheader("🧱 Compilation")
                if compile_info.get("status") == "success":
                    st.success("✅ Compiled successfully.")
                else:
                    st.error(f"❌ Compilation failed:\n\n{compile_info.get('stderr','No output.')}")

                st.subheader("🧩 Static Analysis (Cppcheck)")
                issues = static_info.get("issues", [])
                if issues:
                    st.warning(f"{len(issues)} issues found:")
                    for issue in issues:
                        st.markdown(f"- {issue}")
                else:
                    st.success("No static issues detected.")

                st.subheader("🧪 Functional Testing")
                if not test_info:
                    st.info("No test cases executed.")
                else:
                    total = len(test_info)
                    passed = sum(1 for t in test_info if t["success"])
                    st.metric("📊 Tests Passed", f"{passed}/{total}")
                    for i, t in enumerate(test_info, 1):
                        with st.expander(f"Test {i}: {'✅ Passed' if t['success'] else '❌ Failed'}"):
                            st.write(f"**Input:** `{t['input']}`")
                            st.write(f"**Expected:** `{t['expected']}`")
                            st.write(f"**Actual:** `{t['actual']}`")
                            st.write(f"**Comment:** {t['comment']}")

                st.subheader("⚙️ Performance")
                st.info(perf_info.get("comment", "Performance data not available."))

                st.subheader("🏆 Final Score")
                st.metric("Final Score", f"{final_score}/100")

            with right:
                st.subheader("📘 Gemini 2.5 Flash Feedback Report")
                with st.spinner("Generating AI feedback report..."):
                    try:
                        report_text = llm_agents.generate_llm_report(evaluation)
                    except Exception as e:
                        report_text = f"Gemini report generation failed: {e}"

                safe_html = report_text.replace("\n", "<br/>")
                st.markdown(f"<div class='report-box'>{safe_html}</div>", unsafe_allow_html=True)

                # PDF Generation
                def generate_pdf(report: str) -> BytesIO:
                    buffer = BytesIO()
                    doc = SimpleDocTemplate(buffer, pagesize=A4)
                    styles = getSampleStyleSheet()
                    story = [
                        Paragraph("<b>C Autograder Evaluation Report</b>", styles["Title"]),
                        Spacer(1, 12),
                        Paragraph(f"<b>Final Score:</b> {final_score}/100", styles["Normal"]),
                        Spacer(1, 12),
                        Paragraph("<b>Detailed Feedback</b>", styles["Heading2"]),
                        Paragraph(report.replace("\n", "<br/>"), styles["Normal"]),
                        Spacer(1, 20),
                        Paragraph("<b>Generated via Gemini 2.5 Flash</b>", styles["Italic"])
                    ]
                    doc.build(story)
                    buffer.seek(0)
                    return buffer

                pdf_bytes = generate_pdf(report_text)
                st.download_button(
                    "📥 Download Report (PDF)",
                    data=pdf_bytes,
                    file_name="C_Autograder_Report.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

# ------------------ Step 4: Diagnostics ------------------
with st.expander("⚙️ Step 4 – Environment Diagnostics", expanded=False):
    with st.spinner("Running environment checks..."):
        env_info = {
            "GCC Installed": os.system("which gcc > /dev/null") == 0,
            "Cppcheck Installed": os.system("which cppcheck > /dev/null") == 0,
            "Groq API Key": bool(os.getenv("GROQ_API_KEY")),
            "Gemini API Key": bool(os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        }
    st.json(env_info)
    try:
        st.success(llm_agents.test_gemini_connection())
    except Exception as e:
        st.error(f"Gemini test failed: {e}")

# ------------------ Footer ------------------
st.markdown("<div class='footer'>C Autograder · Unified Workflow · Powered by Groq OSS 20B + Gemini 2.5 Flash</div>", unsafe_allow_html=True)
