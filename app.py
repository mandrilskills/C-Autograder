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
    page_title="C Autograder | Groq OSS 20B + Gemini 2.5 Flash",
    layout="wide",
    page_icon="🎓"
)

# ---------------------------------------------------------------------
# STYLING – MODERN DARK NEON BLUE THEME
# ---------------------------------------------------------------------
st.markdown("""
<style>
    html, body, .main {
        background: linear-gradient(135deg, #0a0f1f 0%, #0d1628 50%, #111a2f 100%);
        color: #e2e8f0;
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3 {
        color: #6ecbff;
        font-weight: 600;
        letter-spacing: 0.3px;
    }
    .stButton>button {
        background-color: #2563eb;
        color: #f8fafc;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.6rem 1.2rem;
        transition: 0.3s ease-in-out;
    }
    .stButton>button:hover {
        background-color: #1e40af;
        transform: scale(1.03);
    }
    .section-card {
        background: rgba(20, 25, 35, 0.7);
        border: 1px solid #1f2a40;
        border-radius: 12px;
        padding: 22px 28px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.4);
        margin-bottom: 30px;
        backdrop-filter: blur(10px);
    }
    .report-box {
        background: rgba(15, 20, 35, 0.85);
        border: 1px solid #1d2a4f;
        border-radius: 10px;
        padding: 16px;
        color: #d9e2f1;
    }
    .stTextInput>div>div>input, textarea {
        background-color: rgba(25, 30, 45, 0.85) !important;
        color: #e2e8f0 !important;
        border-radius: 8px !important;
        border: 1px solid #334155 !important;
    }
    .footer {
        text-align: center;
        color: #9ca3af;
        font-size: 13px;
        margin-top: 40px;
    }
    hr {
        border: 0.5px solid #1f2a40;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------
st.markdown("<h1 style='text-align:center;'>C Autograder</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#cbd5e1;'>Groq OSS 20B + Gemini 2.5 Flash – Intelligent Code Evaluation Platform</p>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# STEP 1 – UPLOAD CODE
# ---------------------------------------------------------------------
st.subheader("Step 1 – Upload or Paste Your C Code")
st.markdown("Upload your `.c` source file or paste your code below to start the evaluation process.")

uploaded = st.file_uploader("Upload a `.c` file", type=["c"])
code_text = uploaded.read().decode("utf-8") if uploaded else st.text_area(
    "Or paste your code here:", height=250, placeholder="// Enter your C program..."
)

if code_text:
    st.success("✅ Code loaded successfully. You can now generate test cases.")
    st.session_state["code_text"] = code_text
else:
    st.info("Please upload or paste valid C code to proceed.")

# ---------------------------------------------------------------------
# STEP 2 – GENERATE TEST CASES
# ---------------------------------------------------------------------
st.markdown("<hr>", unsafe_allow_html=True)
st.subheader("Step 2 – Generate Test Cases (Groq OSS 20B)")

code_text = st.session_state.get("code_text", "")
if not code_text:
    st.warning("Please complete Step 1 before generating test cases.")
else:
    if st.button("Generate Test Cases"):
        with st.spinner("Analyzing code and generating test cases via Groq OSS 20B..."):
            res = generate_test_cases_with_logging(code_text)
        if res["status"] in ["ok", "fallback"]:
            st.session_state["tests"] = "\n".join(res["tests"])
            st.success(f"{len(res['tests'])} test cases generated successfully.")
            st.text_area("Generated Test Cases (editable):", st.session_state["tests"], height=200)
        else:
            st.error(f"Test generation failed: {res['reason']}")

# ---------------------------------------------------------------------
# STEP 3 – RUN EVALUATION
# ---------------------------------------------------------------------
st.markdown("<hr>", unsafe_allow_html=True)
st.subheader("Step 3 – Run Evaluation and Generate Report")

code_text = st.session_state.get("code_text", "")
tests_raw = st.session_state.get("tests", "")

if st.button("Run Evaluation"):
    if not code_text:
        st.error("Please upload your C code first.")
    else:
        left, right = st.columns([0.55, 0.45])
        with left:
            with st.spinner("Running compilation, static analysis, and test suite..."):
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

            st.markdown("#### Compilation Results")
            if compile_info.get("status") == "success":
                st.success("Compiled successfully.")
            else:
                st.error(f"Compilation failed:\n\n{compile_info.get('stderr','No compiler output.')}")

            st.markdown("#### Static Analysis (Cppcheck)")
            issues = static_info.get("issues", [])
            if issues:
                st.warning(f"{len(issues)} issue(s) found.")
                for issue in issues:
                    st.write(f"- {issue}")
            else:
                st.success("No static issues detected.")

            st.markdown("#### Functional Testing")
            if not test_info:
                st.info("No test cases executed.")
            else:
                total = len(test_info)
                passed = sum(1 for t in test_info if t["success"])
                st.metric(label="Tests Passed", value=f"{passed}/{total}")
                for i, t in enumerate(test_info, 1):
                    with st.expander(f"Test {i}: {'Passed ✅' if t['success'] else 'Failed ❌'}"):
                        st.write(f"**Input:** `{t['input']}`")
                        st.write(f"**Expected:** `{t['expected']}`")
                        st.write(f"**Actual:** `{t['actual']}`")
                        st.write(f"**Comment:** {t['comment']}")

            st.markdown("#### Performance")
            st.info(perf_info.get("comment", "Performance not available."))

            st.markdown("#### Final Score")
            st.metric(label="Final Score", value=f"{final_score}/100")

        with right:
            st.markdown("#### Gemini 2.5 Flash Feedback Report")
            with st.spinner("Generating detailed AI feedback..."):
                try:
                    report_text = llm_agents.generate_llm_report(evaluation)
                except Exception as e:
                    report_text = f"Error generating report: {e}"

            safe_html = report_text.replace("\n", "<br/>")
            st.markdown(f"<div class='report-box'>{safe_html}</div>", unsafe_allow_html=True)

            # -------- PDF GENERATION --------
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
                "Download Report (PDF)",
                data=pdf_bytes,
                file_name="C_Autograder_Report.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

# ---------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown("<div class='footer'>© 2025 C Autograder · Powered by Groq OSS 20B + Gemini 2.5 Flash</div>", unsafe_allow_html=True)
