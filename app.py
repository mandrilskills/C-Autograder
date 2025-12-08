# app.py
# ---------------------------------------------------------
# Streamlit UI for C Autograder – Agentic Pipeline
# ---------------------------------------------------------

import streamlit as st
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

# ✅ Import the grader pipeline
from grader_langgraph import run_grader_pipeline

# ✅ Import weights for display
from config import (
    WEIGHT_COMPILATION,
    WEIGHT_FUNCTIONAL,
    WEIGHT_STATIC,
    WEIGHT_PERF,
)

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------

st.set_page_config(
    page_title="C Autograder | Agentic Pipeline",
    layout="wide",
    page_icon="🎓",
)

st.title("🎓 C Autograder – Agentic Evaluation System")

st.caption(
    "• Compilation → Functional Tests → Static Analysis → Performance\n"
    "• Gemini 2.5 Flash generates final feedback\n"
    "• Partial marks are awarded even if compilation fails"
)

# ---------------------------------------------------------
# INPUT AREA
# ---------------------------------------------------------

default_code = """#include <stdio.h>

int main() {
    int a, b;
    scanf("%d %d", &a, &b);
    printf("%d", a + b);
    return 0;
}
"""

col1, col2 = st.columns([2, 1])

with col1:
    uploaded_file = st.file_uploader("Upload C Source Code (.c)", type=["c"])
    st.markdown("---")
    user_code = st.text_area(
        "OR Paste C Source Code Here",
        default_code,
        height=300,
        key="code_input",
    )

with col2:
    st.subheader("Pipeline Control")
    st.info("The agent dynamically routes based on results.")
    run_button = st.button("🚀 Run Autograder", type="primary")

# ---------------------------------------------------------
# PDF BUILDER
# ---------------------------------------------------------

@st.cache_data
def build_pdf(report_data: dict) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("C AUTOGRADER FINAL REPORT", styles["Title"]))
    story.append(Spacer(1, 12))

    # ✅ Marking Scheme Section
    story.append(Paragraph("Marking Scheme", styles["Heading2"]))
    story.append(
        Paragraph(
            f"""
• Compilation: {int(WEIGHT_COMPILATION * 100)}%  
• Functional Tests: {int(WEIGHT_FUNCTIONAL * 100)}%  
• Static Analysis: {int(WEIGHT_STATIC * 100)}%  
• Performance: {int(WEIGHT_PERF * 100)}%  
""",
            styles["Normal"],
        )
    )

    story.append(Spacer(1, 12))

    final_score = report_data.get("final_score", 0.0)
    final_report = report_data.get("final_report", {})

    story.append(
        Paragraph(f"Final Score: {final_score * 100:.2f} / 100", styles["Normal"])
    )
    story.append(Spacer(1, 10))

    story.append(Paragraph("Summary", styles["Heading2"]))
    story.append(
        Paragraph(final_report.get("summary", "No summary available."), styles["Normal"])
    )

    story.append(Spacer(1, 10))
    story.append(Paragraph("Detailed Feedback", styles["Heading2"]))
    story.append(
        Paragraph(
            final_report.get("detailed_feedback", "No feedback available.").replace(
                "\n", "<br/>"
            ),
            styles["Normal"],
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer


# ---------------------------------------------------------
# RUN PIPELINE
# ---------------------------------------------------------

if run_button:
    if uploaded_file is not None:
        code_to_grade = uploaded_file.getvalue().decode("utf-8", errors="ignore")
    elif user_code.strip():
        code_to_grade = user_code
    else:
        st.error("Please upload or paste C code.")
        st.stop()

    with st.spinner("Running agentic pipeline..."):
        results = run_grader_pipeline(code_to_grade)

    st.session_state["results"] = results


# ---------------------------------------------------------
# DISPLAY RESULTS
# ---------------------------------------------------------

if "results" in st.session_state:
    results = st.session_state["results"]

    final_score = results.get("final_score", 0.0)
    final_report = results.get("final_report", {})

    st.markdown("---")

    col_score, col_pdf = st.columns([3, 1])

    with col_score:
        st.metric("Final Score", f"{final_score * 100:.2f} / 100")

    with col_pdf:
        pdf_buffer = build_pdf(results)
        st.download_button(
            label="📄 Download PDF Report",
            data=pdf_buffer,
            file_name="C_Autograder_Report.pdf",
            mime="application/pdf",
        )

    st.markdown("---")
    st.header("✅ Agent Feedback")

    st.subheader(final_report.get("summary", "No summary generated."))
    st.markdown(final_report.get("detailed_feedback", ""))

    st.markdown("---")
    st.header("📊 Diagnostics (Bullet Format)")

    # ✅ Compilation
    with st.expander("🛠 Compilation Info"):
        c = results.get("compile_info", {})
        st.markdown(
            f"""
• Status: {c.get("status")}
• Errors:
{c.get("stderr", "None")}
"""
        )

    # ✅ Test cases
    with st.expander("✅ Test Cases Used"):
        for t in results.get("test_info", {}).get("test_results", []):
            st.markdown(
                f"• Input: `{t.get('input')}` → Expected: `{t.get('expected')}`"
            )

    # ✅ Test results
    with st.expander("📋 Functional Test Results"):
        for t in results.get("test_info", {}).get("test_results", []):
            st.markdown(
                f"• Input: `{t.get('input')}` | "
                f"Expected: `{t.get('expected')}` | "
                f"Actual: `{t.get('actual')}` | "
                f"Passed: {t.get('passed')}"
            )

    # ✅ Static analysis
    with st.expander("📐 Static Analysis"):
        issues = results.get("static_info", {}).get("issues", [])
        if issues:
            for issue in issues:
                st.markdown(f"• {issue}")
        else:
            st.markdown("• No major static issues detected.")

    # ✅ Performance
    with st.expander("⚡ Performance Info"):
        p = results.get("perf_info", {})
        st.markdown(
            f"""
• Execution Time: {p.get("execution_time_ms")} ms  
• Memory Used: {p.get("memory_kb")} KB
"""
        )
