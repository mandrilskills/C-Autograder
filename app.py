# app.py

import streamlit as st
import os
import json
import logging
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

# Local imports
import llm_agents
from llm_agents import generate_test_cases_with_logging
from grader_langgraph import run_grader_pipeline

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="C Autograder – Groq OSS 20B + Gemini 2.5 Flash",
    layout="wide",
    page_icon="🎓"
)

# ---------------------------------------------------------------------
# DARK THEME STYLING
# ---------------------------------------------------------------------
st.markdown("""
<style>
    body, .main {
        background-color: #0d1117;
        color: #f1f5f9;
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3 {
        color: #ffffff;
        font-weight: 600;
    }
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
    .section-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 20px 25px;
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
    .stTextInput>div>div>input, textarea {
        background-color: #161b22 !important;
        color: #e2e8f0 !important;
        border-radius: 8px !important;
        border: 1px solid #30363d !important;
    }
    .stFileUploader label div div {
        color: #e2e8f0 !important;
    }
    .footer {
        text-align: center;
        color: #94a3b8;
        font-size: 13px;
        margin-top: 40px;
    }
    .sidebar .sidebar-content {
        background-color: #161b22 !important;
        color: #e2e8f0 !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# SIDEBAR NAVIGATION
# ---------------------------------------------------------------------
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/906/906175.png", width=60)
st.sidebar.title("C Autograder Panel")
st.sidebar.markdown("Automated grading powered by **Groq OSS 20B** + **Gemini 2.5 Flash**.")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["🏠 Overview", "🧱 Upload Code", "🧪 Generate Test Cases", "🏁 Evaluation & Report", "⚙️ Diagnostics"]
)

st.sidebar.markdown("---")
st.sidebar.caption("Developed by Academic Autograder · © 2025")

# ---------------------------------------------------------------------
# PAGE 1 – OVERVIEW
# ---------------------------------------------------------------------
if page == "🏠 Overview":
    st.title("🎓 C Autograder – Groq OSS 20B + Gemini 2.5 Flash")
    st.markdown("""
    Welcome to **C Autograder**, an AI-driven automated assessment platform for C programs.  
    This tool integrates:
    - 🧠 **Groq OSS 20B** for test generation  
    - 🧩 **Cppcheck + GCC** for static & compile analysis  
    - ⚙️ **Gemini 2.5 Flash** for feedback and grading reports  

    **Workflow:**
    1️⃣ Upload or paste code  
    2️⃣ Auto-generate test cases  
    3️⃣ Run evaluation  
    4️⃣ Download the detailed report
    """)
    st.info("Use the sidebar to get started → Upload your code.")

# ---------------------------------------------------------------------
# PAGE 2 – UPLOAD CODE
# ---------------------------------------------------------------------
elif page == "🧱 Upload Code":
    st.header("Step 1️⃣ – Upload or Paste Your C Code")
    st.markdown("Upload your `.c` file or paste the code below to start the evaluation.")

    uploaded = st.file_uploader("📂 Upload a `.c` file", type=["c"])
    code_text = uploaded.read().decode("utf-8") if uploaded else st.text_area(
        "✏️ Paste your code here:", height=300, placeholder="// Enter your C program..."
    )

    if code_text:
        st.session_state["code_text"] = code_text
        st.success("✅ Code loaded successfully. Proceed to Test Case Generation.")
    else:
        st.warning("Please upload or paste valid C code to continue.")

# ---------------------------------------------------------------------
# PAGE 3 – GENERATE TEST CASES
# ---------------------------------------------------------------------
elif page == "🧪 Generate Test Cases":
    st.header("Step 2️⃣ – Generate Test Cases (Groq OSS 20B)")

    code_text = st.session_state.get("code_text", "")
    if not code_text:
        st.warning("Please upload your code first.")
    else:
        if st.button("🚀 Generate Test Cases"):
            with st.spinner("Generating test cases using Groq OSS 20B..."):
                res = generate_test_cases_with_logging(code_text)
            if res["status"] in ["ok", "fallback"]:
                st.session_state["tests"] = "\n".join(res["tests"])
                st.success(f"✅ {len(res['tests'])} test cases generated.")
                st.text_area("🧾 Generated Test Cases", st.session_state["tests"], height=200)
            else:
                st.error(f"❌ Test generation failed: {res['reason']}")

# ---------------------------------------------------------------------
# PAGE 4 – RUN EVALUATION
# ---------------------------------------------------------------------
elif page == "🏁 Evaluation & Report":
    st.header("Step 3️⃣ – Run Evaluation and Generate Report")

    code_text = st.session_state.get("code_text", "")
    tests_raw = st.session_state.get("tests", "")

    if st.button("🏁 Run Evaluation"):
        if not code_text:
            st.error("Please upload or paste your code first.")
        else:
            left, right = st.columns([0.55, 0.45])
            with left:
                with st.spinner("Running compilation, analysis, and tests..."):
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

                st.subheader("🧱 Compilation Results")
                if compile_info.get("status") == "success":
                    st.success("✅ Compiled successfully.")
                else:
                    st.error(f"❌ Compilation failed:\n\n{compile_info.get('stderr','No output.')}")

                st.subheader("🧩 Static Analysis (Cppcheck)")
                issues = static_info.get("issues", [])
                if issues:
                    st.warning(f"{len(issues)} issues found.")
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
                st.subheader("📘 Gemini 2.5 Flash Report")
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

# ---------------------------------------------------------------------
# PAGE 5 – DIAGNOSTICS
# ---------------------------------------------------------------------
elif page == "⚙️ Diagnostics":
    st.header("System Diagnostics")
    st.markdown("Verify compiler tools and API connections.")

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

# ---------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------
st.markdown("<div class='footer'>C Autograder · Dark Mode · Powered by Groq OSS 20B + Gemini 2.5 Flash</div>", unsafe_allow_html=True)
