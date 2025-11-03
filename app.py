# app.py
import streamlit as st
import os
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
import json
import logging

# imports from local modules
import llm_agents
from llm_agents import generate_test_cases_with_logging
from grader_langgraph import run_grader_pipeline

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page setup
st.set_page_config(page_title="C Autograder – Groq OSS 20B + Gemini 2.5 Flash", layout="wide")

st.title("🎓 C Autograder – Groq OSS 20B + Gemini 2.5 Flash")
st.caption("Groq (openai/gpt-oss-20b) → Test cases · GCC/Cppcheck → Evaluation · Gemini 2.5 Flash → Report")

# ---------------- Diagnostics ----------------
with st.expander("🔧 Environment Diagnostics"):
    env_info = {
        "gcc": os.system("which gcc > /dev/null") == 0,
        "cppcheck": os.system("which cppcheck > /dev/null") == 0,
        "groq_api": bool(os.getenv("GROQ_API_KEY")),
        "genai_api": bool(os.getenv("GENAI_API_KEY")),
    }
    st.json(env_info)
    try:
        st.text(llm_agents.test_gemini_connection())
    except Exception as e:
        st.write(f"Gemini connection test failed: {e}")

# ---------------- Code Input ----------------
st.header("1️⃣ Upload or Paste C Code")
uploaded = st.file_uploader("Upload a .c file", type=["c"])
code_text = uploaded.read().decode("utf-8") if uploaded else st.text_area("Paste your C code here:", height=300)

# ---------------- Test Case Generation ----------------
if st.button("🚀 Generate Test Cases (Groq OSS 20B)"):
    if not code_text or not code_text.strip():
        st.error("Please enter valid C code first.")
    else:
        with st.spinner("Generating test cases using Groq (openai/gpt-oss-20b)..."):
            res = generate_test_cases_with_logging(code_text)
        st.success(f"Status: {res['status']} — {res.get('reason','')}")
        st.session_state["tests"] = "\n".join(res["tests"])
        st.text_area("Generated Test Cases (Editable)", st.session_state["tests"], height=200)

# ---------------- Evaluation ----------------
st.header("2️⃣ Run Evaluation and Generate Report")
if st.button("🏁 Run Evaluation"):
    if not code_text or not code_text.strip():
        st.warning("Please provide a valid C program first.")
    else:
        # Split layout: Left = Evaluation, Right = Report
        left, right = st.columns([0.55, 0.45])

        # ---------- LEFT PANEL: Evaluation ----------
        with left:
            with st.spinner("Running compilation, static analysis, and tests..."):
                evaluation = run_grader_pipeline(
                    code_text,
                    st.session_state.get("tests", "").splitlines(),
                    llm_reporter=llm_agents.generate_llm_report,
                )

            compile_info = evaluation.get("compile", {})
            static_info = evaluation.get("static", {})
            test_info = evaluation.get("test", {}).get("results", [])
            perf_info = evaluation.get("perf", {})
            final_score = evaluation.get("final_score", 0)
            score_breakdown = evaluation.get("score_breakdown", {
                "Compilation": 20,
                "Static Analysis": 20,
                "Functional": 50,
                "Performance": 10
            })

            st.success("✅ Evaluation Completed")

            # Compilation summary
            st.markdown("### 🧱 Compilation")
            if compile_info.get("status") == "success":
                st.write("✅ Code compiled successfully using GCC.")
            else:
                st.error(f"❌ Compilation failed:\n\n{compile_info.get('stderr', 'No message available.')}")

            # Static analysis
            st.markdown("### 🧩 Static Analysis (Cppcheck)")
            issues = static_info.get("issues", [])
            if issues:
                st.warning(f"{len(issues)} issue(s) found:")
                for issue in issues:
                    st.write(f"• {issue}")
            else:
                st.write("✅ No static issues detected.")

            # Test results
            st.markdown("### 🧪 Functional Testing")
            if not test_info:
                st.info("No test cases executed.")
            else:
                total = len(test_info)
                passed = sum(1 for t in test_info if t["success"])
                st.write(f"📊 **{passed}/{total} Tests Passed**")
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

            # Performance
            st.markdown("### ⚙️ Performance")
            st.write(perf_info.get("comment", "Performance not recorded."))

            # Score breakdown
            st.markdown("### 🧮 Score Breakdown")
            st.write(f"**Compilation:** {score_breakdown.get('Compilation', 0)}/20")
            st.write(f"**Static Analysis:** {score_breakdown.get('Static Analysis', 0)}/20")
            st.write(f"**Functional Testing:** {score_breakdown.get('Functional', 0)}/50")
            st.write(f"**Performance:** {score_breakdown.get('Performance', 0)}/10")

            st.metric(label="🏆 Final Score", value=f"{final_score} / 100")

        # ---------- RIGHT PANEL: Gemini Report ----------
        with right:
            st.markdown("### 📘 Gemini 2.5 Flash Report")

            # Try Gemini normally first
            report_text = None
            try:
                with st.spinner("Generating student-friendly report (Gemini 2.5 Flash)..."):
                    report_text = llm_agents.generate_llm_report(evaluation)
            except Exception as e:
                logger.warning(f"Gemini report generation failed: {e}")

            def is_valid_report(text):
                return bool(text) and isinstance(text, str) and len(text.strip()) > 60

            # Retry if report is too short or missing
            if not is_valid_report(report_text):
                logger.info("Primary Gemini report empty — retrying with explicit simple-language prompt.")
                try:
                    simple_prompt = (
                        "You are an AI teacher explaining this code evaluation to students.\n"
                        "Given the JSON below, explain in simple language:\n"
                        "- Whether the code compiled or not\n"
                        "- What static issues were found\n"
                        "- Why tests failed (if any)\n"
                        "- Suggest clear improvements\n"
                        "- If available provide a rectified and better code of the same problem else do not\n"
                        "- Conclude with an overall comment.\n\n"
                        f"Evaluation JSON:\n{json.dumps(evaluation, indent=2)}"
                    )
                    report_text = llm_agents._call_gemini(simple_prompt, max_output_tokens=1200)
                except Exception as e:
                    logger.warning(f"Gemini retry failed: {e}")
                    report_text = None

            # Final fallback if still empty
            if not is_valid_report(report_text):
                logger.warning("Gemini report unavailable after retry — using fallback summary.")
                fallback_lines = []
                if compile_info.get("status") == "success":
                    fallback_lines.append("Compilation: Your program compiled successfully.")
                else:
                    fallback_lines.append("Compilation: Your program failed to compile. Please fix syntax errors.")
                    if compile_info.get("stderr"):
                        fallback_lines.append(f"Compiler output: {compile_info.get('stderr')}")
                if static_info.get("issues"):
                    fallback_lines.append(f"Static Analysis: {len(static_info.get('issues'))} issue(s) found.")
                    for it in static_info.get("issues")[:3]:
                        fallback_lines.append(f"- {it}")
                else:
                    fallback_lines.append("Static Analysis: No major issues detected.")
                if test_info:
                    passed = sum(1 for t in test_info if t["success"])
                    total = len(test_info)
                    fallback_lines.append(f"Functional Tests: {passed}/{total} passed.")
                    if passed < total:
                        fallback_lines.append("Tip: Ensure no extra print prompts like 'Enter number:' appear in automated outputs.")
                perf_comment = perf_info.get("comment", "")
                if perf_comment:
                    fallback_lines.append(f"Performance: {perf_comment}")
                fallback_lines.append(f"Overall Score: {final_score}/100.")
                report_text = "\n\n".join(fallback_lines)

            # Safe HTML conversion (fixed syntax)
            safe_html = report_text.replace("\n", "<br/>")

            # Display as styled non-editable section
            st.markdown(
                f"""
                <div style="
                    background-color: #fbfbfb;
                    padding: 16px;
                    border-radius: 12px;
                    border: 1px solid #e2e2e2;
                    color: #111;">
                    {safe_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

            # -------- PDF Generation --------
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
                story.append(Paragraph("<b>Generated via Gemini 2.5 Flash (or fallback)</b>", styles["Italic"]))
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

            st.caption("If Gemini output was limited, a retry or fallback summary was generated to ensure full feedback.")

