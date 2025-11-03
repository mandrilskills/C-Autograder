# app.py (updated - robust Gemini report handling + split view + PDF)
import streamlit as st
import os
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
import json
import logging

# import the functions; llm_agents contains generate_llm_report and internal _call_gemini
import llm_agents
from llm_agents import generate_test_cases_with_logging
from grader_langgraph import run_grader_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="C Autograder – Groq OSS 20B + Gemini 2.5 Flash", layout="wide")

st.title("🎓 C Autograder – Groq OSS 20B + Gemini 2.5 Flash")
st.caption("Groq (openai/gpt-oss-20b) → Test cases · GCC/Cppcheck → Evaluation · Gemini 2.5 Flash → Report")

# Diagnostics
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

# Code input
st.header("1️⃣ Upload or Paste C Code")
uploaded = st.file_uploader("Upload a .c file", type=["c"])
code_text = uploaded.read().decode("utf-8") if uploaded else st.text_area("Paste your C code here:", height=300)

# Test case generation
if st.button("🚀 Generate Test Cases (Groq OSS 20B)"):
    if not code_text or not code_text.strip():
        st.error("Please enter valid C code first.")
    else:
        with st.spinner("Generating test cases using Groq (openai/gpt-oss-20b)..."):
            res = generate_test_cases_with_logging(code_text)
        st.success(f"Status: {res['status']} — {res.get('reason','')}")
        st.session_state["tests"] = "\n".join(res["tests"])
        st.text_area("Generated Test Cases (Editable)", st.session_state["tests"], height=200)

# Evaluation and report generation
st.header("2️⃣ Run Evaluation and Generate Report")
if st.button("🏁 Run Evaluation"):
    if not code_text or not code_text.strip():
        st.warning("Please provide a valid C program first.")
    else:
        # left: evaluation, right: report
        left, right = st.columns([0.55, 0.45])

        with left:
            with st.spinner("Running compilation, static analysis, and tests..."):
                evaluation = run_grader_pipeline(
                    code_text,
                    st.session_state.get("tests", "").splitlines(),
                    llm_reporter=llm_agents.generate_llm_report,  # normal reporter
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

            # Compilation
            st.markdown("### 🧱 Compilation")
            if compile_info.get("status") == "success":
                st.write("✅ Code compiled successfully using GCC.")
            else:
                st.error(f"❌ Compilation failed:\n\n{compile_info.get('stderr', 'No message available.')}")

            # Static
            st.markdown("### 🧩 Static Analysis (Cppcheck)")
            issues = static_info.get("issues", [])
            if issues:
                st.warning(f"{len(issues)} issue(s) found:")
                for issue in issues:
                    st.write(f"• {issue}")
            else:
                st.write("✅ No static issues detected.")

            # Functional tests
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

        # RIGHT PANEL: Gemini report (non-editable) and PDF download
        with right:
            st.markdown("### 📘 Gemini 2.5 Flash Report")

            # 1) Primary attempt: use standard reporter (which expects evaluation dict)
            report_text = None
            try:
                with st.spinner("Generating student-friendly report (Gemini 2.5 Flash)..."):
                    report_text = llm_agents.generate_llm_report(evaluation)
            except Exception as e:
                logger.warning(f"generate_llm_report raised: {e}")
                report_text = None

            # Check if result is usable
            def is_valid_report(s: str) -> bool:
                return bool(s) and isinstance(s, str) and len(s.strip()) > 60

            # 2) If short/empty, retry with an explicit simple-language prompt via internal call
            if not is_valid_report(report_text):
                logger.info("Primary Gemini report empty/short — attempting one retry with explicit simple prompt.")
                try:
                    simple_prompt = (
                        "You are an assistant explaining evaluation results to students in plain English.\n\n"
                        "Given this evaluation JSON, produce a clear and detailed feedback report in simple language. "
                        "Explain compilation status, static analysis issues (if any), why tests failed (if any), and give 3 practical improvement tips. "
                        "Keep it educational and avoid heavy technical jargon. Be specific where possible.\n\n"
                        f"Evaluation JSON:\n{json.dumps(evaluation, indent=2)}"
                    )
                    # Use internal call directly to _call_gemini (2.5 flash only)
                    # _call_gemini is internal to llm_agents; we access it intentionally for retry.
                    report_text = llm_agents._call_gemini(simple_prompt, max_output_tokens=1200)
                except Exception as e:
                    logger.warning(f"Retry via _call_gemini failed: {e}")
                    report_text = None

            # 3) If still invalid, produce deterministic fallback summary so student always gets useful info
            if not is_valid_report(report_text):
                logger.warning("Gemini report unavailable after retry — creating fallback student-friendly report locally.")
                # Build a friendly fallback
                lines = []
                # Compilation
                if compile_info.get("status") == "success":
                    lines.append("Compilation: Your program compiled successfully.")
                else:
                    lines.append("Compilation: Your program failed to compile. Check the compiler error messages and fix syntax/typos.")
                    if compile_info.get("stderr"):
                        lines.append(f"Compiler messages: {compile_info.get('stderr')}")
                # Static
                if static_info.get("issues"):
                    lines.append(f"Static Analysis: {len(static_info.get('issues'))} issue(s) found. Examples:")
                    for it in static_info.get("issues")[:3]:
                        lines.append(f"- {it}")
                    lines.append("Suggestion: Address the reported warnings; they often point to portability or correctness issues.")
                else:
                    lines.append("Static Analysis: No major issues reported by Cppcheck.")
                # Tests
                if not test_info:
                    lines.append("Functional Tests: No test cases were run.")
                else:
                    passed = sum(1 for t in test_info if t["success"])
                    total = len(test_info)
                    lines.append(f"Functional Tests: {passed}/{total} passed.")
                    for t in test_info[:5]:
                        status = "passed" if t["success"] else "failed"
                        lines.append(f"- Test input `{t['input']}` {status}. Expected `{t['expected']}`, got `{t['actual']}`.")
                    if passed < total:
                        lines.append("Suggestion: Check output formatting and remove extra prompts like 'Enter...' so automated checks match your output.")
                # Performance
                perf_comment = perf_info.get("comment", "")
                if perf_comment:
                    lines.append(f"Performance: {perf_comment}")
                # Final
                lines.append(f"Overall: Final Score = {final_score}/100. Keep iterating—focus on fixing failing tests and static warnings.")
                report_text = "\n\n".join(lines)

            # Display (styled, non-editable)
            st.markdown(
                f"""
                <div style="
                    background-color: #fbfbfb;
                    padding: 16px;
                    border-radius: 12px;
                    border: 1px solid #e2e2e2;
                    color: #111;">
                    {report_text.replace('\n', '<br/>')}
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Provide user info if we had to retry/fallback
            if not llm_agents or not report_text:
                st.warning("Report may be incomplete. A fallback summary was shown.")
            else:
                # If original generate_llm_report returned short and we retried, inform user
                # (We use heuristic: if first attempt returned something but short; that info isn't tracked here, so keep minimal)
                pass

            # PDF generation (always provide)
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
                # keep newlines
                story.append(Paragraph(report.replace("\n", "<br/>"), styles["Normal"]))
                story.append(Spacer(1, 20))
                story.append(Paragraph("<b>Generated via Gemini 2.5 Flash (or local fallback)</b>", styles["Italic"]))
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

            st.caption("If the report looks short, the system retried the LLM and provided a local fallback to ensure you always receive helpful feedback.")
