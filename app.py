# app.py
import streamlit as st
import os
import tempfile
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from llm_agents import generate_test_cases_with_logging, generate_llm_report, test_gemini_connection
from grader_langgraph import run_grader_pipeline

st.set_page_config(page_title="C Autograder – OSS 20B + Gemini 2.5 Flash", layout="wide")

st.title("🎓 C Autograder – Groq OSS 20B + Gemini 2.5 Flash")
st.caption("Groq (openai/gpt-oss-20b) for test cases · GCC/Cppcheck for evaluation · Gemini 2.5 Flash for report")

# ---------------- Diagnostics ----------------
st.subheader("Environment Diagnostics")
env_info = {
    "gcc": os.system("which gcc > /dev/null") == 0,
    "cppcheck": os.system("which cppcheck > /dev/null") == 0,
    "groq_api": bool(os.getenv("GROQ_API_KEY")),
    "genai_api": bool(os.getenv("GENAI_API_KEY")),
}
st.json(env_info)

with st.expander("🔗 Test Gemini 2.5 Flash Connection"):
    st.text(test_gemini_connection())

# ---------------- Code Input ----------------
st.header("1️⃣ Upload or Paste C Code")
uploaded = st.file_uploader("Upload a .c file", type=["c"])
code_text = uploaded.read().decode("utf-8") if uploaded else st.text_area("Paste your C code here:", height=300)

# ---------------- Test Case Generation ----------------
if st.button("🚀 Generate Test Cases (Groq OSS 20B)"):
    if not code_text.strip():
        st.error("Please enter valid C code first.")
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
        st.warning("Please provide a C program first.")
    else:
        with st.spinner("Running full evaluation..."):
            evaluation = run_grader_pipeline(
                code_text,
                st.session_state.get("tests", "").splitlines(),
                llm_reporter=generate_llm_report,
            )

        # Extract key sections
        compile_info = evaluation.get("compile", {})
        static_info = evaluation.get("static", {})
        test_info = evaluation.get("test", {}).get("results", [])
        perf_info = evaluation.get("perf", {})
        final_score = evaluation.get("final_score", 0)

        # ------------- Human-Readable Display -------------
        st.success("✅ Evaluation Completed Successfully!")

        st.markdown("### 🧱 Compilation Summary")
        if compile_info.get("status") == "success":
            st.write("✅ Code compiled successfully using GCC.")
        else:
            st.error(f"❌ Compilation failed.\n\n**Error:** {compile_info.get('stderr','No error output')}")

        st.markdown("### 🧩 Static Analysis (Cppcheck)")
        issues = static_info.get("issues", [])
        if issues:
            st.warning(f"{len(issues)} issue(s) found during static analysis:")
            for issue in issues:
                st.write(f"• {issue}")
        else:
            st.write("✅ No static issues detected by Cppcheck.")

        st.markdown("### 🧪 Functional Test Results")
        if not test_info:
            st.write("⚠️ No test cases executed.")
        else:
            total_tests = len(test_info)
            passed = sum(1 for t in test_info if t["success"])
            st.write(f"📊 **{passed}/{total_tests} Tests Passed**")
            for i, t in enumerate(test_info, 1):
                st.markdown(
                    f"**Test {i}:**  \n"
                    f"🧮 Input: `{t['input']}`  \n"
                    f"🎯 Expected: `{t['expected']}`  \n"
                    f"💻 Actual: `{t['actual']}`  \n"
                    f"✅ Result: {'Passed' if t['success'] else 'Failed'}  \n"
                    f"💬 Comment: {t['comment']}"
                )
                st.divider()

        st.markdown("### ⚙️ Performance Evaluation")
        st.write(perf_info.get("comment", "No performance data recorded."))

        st.markdown("### 🏆 Final Score")
        st.metric(label="Final Score", value=f"{final_score} / 100")

        # ---------------- Gemini Report ----------------
        with st.spinner("Generating detailed Gemini 2.5 Flash report..."):
            report_text = evaluation["report"]

        st.markdown("### 📘 Gemini 2.5 Flash Report")
        st.text_area("Report Content", report_text, height=300)

        # ---------------- PDF Generation ----------------
        def generate_pdf(report_content: str) -> BytesIO:
            """Generate a PDF file from Gemini report using ReportLab."""
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []

            story.append(Paragraph("<b>C Autograder Evaluation Report</b>", styles["Title"]))
            story.append(Spacer(1, 12))
            story.append(Paragraph("<b>Evaluation Summary</b>", styles["Heading2"]))
            story.append(Paragraph(f"Final Score: {final_score}/100", styles["Normal"]))
            story.append(Spacer(1, 12))
            story.append(Paragraph("<b>Gemini 2.5 Flash Generated Report</b>", styles["Heading2"]))
            story.append(Paragraph(report_content.replace("\n", "<br/>"), styles["Normal"]))

            doc.build(story)
            buffer.seek(0)
            return buffer

        pdf_bytes = generate_pdf(report_text)
        st.download_button(
            "📥 Download Detailed PDF Report",
            data=pdf_bytes,
            file_name="C_Autograder_Report.pdf",
            mime="application/pdf",
        )

        st.info("✅ Report successfully generated using Gemini 2.5 Flash.")
