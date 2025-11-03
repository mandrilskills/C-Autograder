# app.py
import streamlit as st
import os
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from llm_agents import generate_test_cases_with_logging, generate_llm_report, test_gemini_connection
from grader_langgraph import run_grader_pipeline

# ---------------- Page Config ----------------
st.set_page_config(
    page_title="C Autograder – OSS 20B + Gemini 2.5 Flash",
    layout="wide"
)

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
        st.session_state["tests"] = "\n".join(res["tests"])
        st.text_area("Generated Test Cases (Editable)", st.session_state["tests"], height=200)

# ---------------- Evaluation ----------------
st.header("2️⃣ Run Evaluation and Generate Report")
if st.button("🏁 Run Evaluation"):
    if not code_text.strip():
        st.warning("Please provide a valid C program first.")
    else:
        # Layout split: Left (Evaluation) | Right (Gemini Report)
        left, right = st.columns([0.55, 0.45])

        with left:
            with st.spinner("Running compilation, static analysis, and testing..."):
                evaluation = run_grader_pipeline(
                    code_text,
                    st.session_state.get("tests", "").splitlines(),
                    llm_reporter=generate_llm_report,
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

            # ---------------- Human Readable Summary ----------------
            st.markdown("### 🧱 Compilation")
            if compile_info.get("status") == "success":
                st.write("✅ Code compiled successfully using GCC.")
            else:
                st.error(f"❌ Compilation failed:\n\n{compile_info.get('stderr', 'No message available.')}")

            st.markdown("### 🧩 Static Analysis (Cppcheck)")
            issues = static_info.get("issues", [])
            if issues:
                st.warning(f"{len(issues)} issue(s) found:")
                for issue in issues:
                    st.write(f"• {issue}")
            else:
                st.write("✅ No static issues detected.")

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

            st.markdown("### ⚙️ Performance")
            st.write(perf_info.get("comment", "Performance not recorded."))

            st.markdown("### 🧮 Score Breakdown")
            st.write(f"**Compilation:** {score_breakdown.get('Compilation', 0)}/20")
            st.write(f"**Static Analysis:** {score_breakdown.get('Static Analysis', 0)}/20")
            st.write(f"**Functional Testing:** {score_breakdown.get('Functional', 0)}/50")
            st.write(f"**Performance:** {score_breakdown.get('Performance', 0)}/10")

            st.metric(label="🏆 Final Score", value=f"{final_score} / 100")

        # ---------------- Gemini Report (RIGHT PANEL) ----------------
        with right:
            st.markdown("### 📘 Gemini 2.5 Flash Report")

            with st.spinner("Generating a simple and student-friendly report..."):
                prompt = f"""
You are an assistant that explains program evaluation to students.

Given the following JSON evaluation:
{evaluation}

Write a clear, non-technical feedback report:
- Explain compilation success/failure in simple words.
- Describe static analysis results simply.
- Explain failed test cases in plain English.
- Suggest easy improvements (avoid compiler jargon).
- Conclude with overall performance feedback.
"""
                report_text = generate_llm_report(prompt)

            # Non-editable readable output box (styled paragraph)
            st.markdown(
                f"""
                <div style="
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 12px;
                    line-height: 1.6;
                    border: 1px solid #ddd;
                    color: #222;">
                    {report_text}
                </div>
                """,
                unsafe_allow_html=True,
            )

            # ---------------- PDF Export ----------------
            def generate_pdf(report: str) -> BytesIO:
                buffer = BytesIO()
                doc = SimpleDocTemplate(buffer, pagesize=A4)
                styles = getSampleStyleSheet()
                story = []

                story.append(Paragraph("<b>C Autograder Evaluation Report</b>", styles["Title"]))
                story.append(Spacer(1, 12))
                story.append(Paragraph(f"<b>Final Score:</b> {final_score}/100", styles["Normal"]))
                story.append(Spacer(1, 10))
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
            st.caption("Gemini 2.5 Flash generated this simplified educational report.")
