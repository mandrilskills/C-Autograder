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
# CUSTOM CSS STYLING
# ---------------------------------------------------------------------
st.markdown("""
<style>
    .main {
        background-color: #f9fafb;
        font-family: 'Inter', sans-serif;
        color: #111827;
    }
    h1, h2, h3 {
        color: #1e293b;
        font-weight: 600;
    }
    .stButton>button {
        border-radius: 8px;
        background-color: #2563eb;
        color: white;
        font-weight: 600;
        transition: 0.3s;
    }
    .stButton>button:hover {
        background-color: #1d4ed8;
    }
    .section-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 20px 25px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.05);
        margin-bottom: 25px;
    }
    .report-box {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 16px;
        color: #111;
    }
    .footer {
        text-align: center;
        color: #64748b;
        font-size: 13px;
        margin-top: 40px;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# SIDEBAR NAVIGATION
# ---------------------------------------------------------------------
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/906/906175.png", width=60)
st.sidebar.title("C Autograder Panel")
st.sidebar.markdown("An automated grading assistant powered by **Groq OSS 20B** and **Gemini 2.5 Flash**.")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    ["🏠 Overview", "🧱 Upload Code", "🧪 Generate Test Cases", "🏁 Evaluation & Report", "⚙️ Diagnostics"]
)

st.sidebar.markdown("---")
st.sidebar.caption("Developed with ❤️ using Streamlit · © 2025 Academic Autograder Suite")

# ---------------------------------------------------------------------
# PAGE 1 – OVERVIEW
# ---------------------------------------------------------------------
if page == "🏠 Overview":
    st.title("🎓 C Autograder – Groq OSS 20B + Gemini 2.5 Flash")
    st.markdown("""
    This tool automates **C program evaluation** by integrating:
    - 🧠 **Groq OSS 20B** for intelligent test case generation  
    - 🧩 **Cppcheck + GCC** for static & compile analysis  
    - ⚙️ **Gemini 2.5 Flash** for AI-driven feedback reports  

    **Workflow:**
    1️⃣ Upload or paste C code  
    2️⃣ Auto-generate test cases  
    3️⃣ Evaluate compilation, logic, and performance  
    4️⃣ Receive a structured feedback report  
    """)
    st.markdown("---")
    st.info("Use the sidebar to begin uploading your C code for automated assessment.")

# ---------------------------------------------------------------------
# PAGE 2 – UPLOAD CODE
# ---------------------------------------------------------------------
elif page == "🧱 Upload Code":
    st.header("Step 1️⃣ – Upload or Paste Your C Code")
    st.markdown("Provide your source code below to begin the evaluation process.")

    with st.container():
        uploaded = st.file_uploader("📂 Upload a `.c` file", type=["c"])
        code_text = uploaded.read().decode("utf-8") if uploaded else st.text_area(
            "✏️ Or paste your C code manually:", height=300, placeholder="// Enter your C program here..."
        )

    if code_text:
        st.success("✅ Code loaded successfully. Proceed to 'Generate Test Cases' from the sidebar.")
        st.session_state["code_text"] = code_text
    else:
        st.warning("Please upload or paste a valid C program.")

# ---------------------------------------------------------------------
# PAGE 3 – GENERATE TEST CASES
# ---------------------------------------------------------------------
elif page == "🧪 Generate Test Cases":
    st.header("Step 2️⃣ – Generate Test Cases (Groq OSS 20B)")
    st.markdown("Let **Groq OSS 20B** automatically analyze your program and create suitable test cases.")

    code_text = st.session_state.get("code_text", "")
    if not code_text:
        st.warning("Please upload your code first from the 'Upload Code' section.")
    else:
        if st.button("🚀 Generate Test Cases"):
            with st.spinner("Contacting Groq OSS 20B for intelligent test case generation..."):
                res = generate_test_cases_with_logging(code_text)
            if res["status"] in ["ok", "fallback"]:
                st.session_state["tests"] = "\n".join(res["tests"])
                st.success(f"✅ Test cases generated ({len(res['tests'])} cases). You can edit them below.")
                st.text_area("🧾 Generated Test Cases", st.session_state["tests"], height=200)
            else:
                st.error(f"Test case generation failed: {res['reason']}")

# ---------------------------------------------------------------------
# PAGE 4 – RUN EVALUATION
# ---------------------------------------------------------------------
elif page == "🏁 Evaluation & Report":
    st.header("Step 3️⃣ – Run Evaluation and Generate Report")
    st.markdown("Analyze compilation, static issues, test results, and get AI-based feedback.")

    code_text = st.session_state.get("code_text", "")
    tests_raw = st.session_state.get("tests", "")

    if st.button("🏁 Run Evaluation"):
        if not code_text:
            st.error("Please upload or paste your C code first.")
        else:
            left, right = st.columns([0.55, 0.45])

            with left:
                with st.spinner("Running GCC, Cppcheck, and test suite..."):
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

                # ---------------- COMPILATION ----------------
                st.markdown("### 🧱 Compilation Results")
                if compile_info.get("status") == "success":
                    st.success("✅ Compiled successfully using GCC.")
                else:
                    st.error(f"❌ Compilation failed:\n\n{compile_info.get('stderr', 'No compiler message available.')}")

                # ---------------- STATIC ANALYSIS ----------------
                st.markdown("### 🧩 Static Analysis (Cppcheck)")
                issues = static_info.get("issues", [])
                if issues:
                    st.warning(f"{len(issues)} issue(s) found.")
                    for issue in issues:
                        st.write(f"• {issue}")
                else:
                    st.success("No static issues detected.")

                # ---------------- FUNCTIONAL TESTS ----------------
                st.markdown("### 🧪 Functional Testing")
                if not test_info:
                    st.info("No test cases executed.")
                else:
                    total = len(test_info)
                    passed = sum(1 for t in test_info if t["success"])
                    st.metric(label="📊 Tests Passed", value=f"{passed}/{total}")
                    for i, t in enumerate(test_info, 1):
                        with st.expander(f"Test {i}: {'✅ Passed' if t['success'] else '❌ Failed'}"):
                            st.write(f"**Input:** `{t['input']}`")
                            st.write(f"**Expected:** `{t['expected']}`")
                            st.write(f"**Actual:** `{t['actual']}`")
                            st.write(f"**Comment:** {t['comment']}")

                # ---------------- PERFORMANCE ----------------
                st.markdown("### ⚙️ Performance")
                st.info(perf_info.get("comment", "Performance not recorded."))

                st.markdown("### 🧮 Final Score")
                st.metric(label="🏆 Final Score", value=f"{final_score} / 100")

            with right:
                st.markdown("### 📘 Gemini 2.5 Flash Feedback Report")

                with st.spinner("Generating AI feedback report..."):
                    try:
                        report_text = llm_agents.generate_llm_report(evaluation)
                    except Exception as e:
                        report_text = f"Gemini report generation failed: {e}"

                safe_html = report_text.replace("\n", "<br/>")
                st.markdown(f"<div class='report-box'>{safe_html}</div>", unsafe_allow_html=True)

                # -------- PDF GENERATION --------
                def generate_pdf(report: str) -> BytesIO:
                    buffer = BytesIO()
                    doc = SimpleDocTemplate(buffer, pagesize=A4)
                    styles = getSampleStyleSheet()
                    story = []
                    story.append(Paragraph("<b>C Autograder Evaluation Report</b>", styles["Title"]))
                    story.append(Spacer(1, 12))
                    story.append(Paragraph(f"<b>Final Score:</b> {final_score}/100", styles["Normal"]))
                    story.append(Spacer(1, 12))
                    story.append(Paragraph("<b>Detailed Feedback</b>", styles["Heading2"]))
                    story.append(Paragraph(report.replace("\n", "<br/>"), styles["Normal"]))
                    story.append(Spacer(1, 20))
                    story.append(Paragraph("<b>Generated via Gemini 2.5 Flash</b>", styles["Italic"]))
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
    st.header("System & Environment Diagnostics")
    st.markdown("Check API keys, compilers, and dependency availability.")
    with st.spinner("Running environment checks..."):
        env_info = {
            "gcc_installed": os.system("which gcc > /dev/null") == 0,
            "cppcheck_installed": os.system("which cppcheck > /dev/null") == 0,
            "groq_api_key": bool(os.getenv("GROQ_API_KEY")),
            "gemini_api_key": bool(os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        }
    st.json(env_info)

    try:
        gemini_status = llm_agents.test_gemini_connection()
        st.success(gemini_status)
    except Exception as e:
        st.error(f"Gemini connection failed: {e}")

# ---------------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------------
st.markdown("<div class='footer'>C Autograder · Powered by Groq OSS 20B + Gemini 2.5 Flash</div>", unsafe_allow_html=True)
