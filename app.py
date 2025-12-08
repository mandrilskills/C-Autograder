import streamlit as st
import os
import json
import logging
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

# Local imports
from grader_langgraph import run_grader_pipeline
from config import (
    WEIGHT_COMPILATION,
    WEIGHT_FUNCTIONAL,
    WEIGHT_STATIC,
    WEIGHT_PERF
)

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="C Autograder | Fully Agentic LangGraph",
    layout="wide",
    page_icon="🎓"
)

@st.cache_data
def build_pdf(report_data: dict) -> BytesIO:
    """Builds a PDF report from the final structured report data."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    Story = []

    Story.append(Paragraph("<h1>C Autograder Final Agentic Report</h1>", styles['h1']))
    Story.append(Spacer(1, 12))

    # ✅ MARKING SCHEME (ADDED)
    Story.append(Paragraph("<h2>Marking Scheme</h2>", styles['h2']))
    Story.append(Paragraph(
        f"""
• Compilation: {int(WEIGHT_COMPILATION*100)}%  
• Functional Tests: {int(WEIGHT_FUNCTIONAL*100)}%  
• Static Analysis: {int(WEIGHT_STATIC*100)}%  
• Performance: {int(WEIGHT_PERF*100)}%  
""",
        styles["Normal"]
    ))
    Story.append(Spacer(1, 18))

    final_score = report_data.get('final_score', 'N/A')
    summary = report_data.get('final_report', {}).get('summary', 'No summary available.')

    Story.append(Paragraph(f"<h2>Final Score: {final_score:.2f} / 1.00</h2>", styles['h2']))
    Story.append(Paragraph(f"<b>Summary:</b> {summary}", styles['Normal']))
    Story.append(Spacer(1, 24))

    feedback_text = report_data.get('final_report', {}).get(
        'detailed_feedback', 'Detailed feedback could not be retrieved.'
    )
    Story.append(Paragraph("<h2>Detailed Agent Feedback (Gemini 2.5 Flash)</h2>", styles['h2']))
    formatted_feedback = feedback_text.replace('\n', '<br/>')
    Story.append(Paragraph(formatted_feedback, styles['Normal']))
    Story.append(Spacer(1, 24))

    Story.append(Paragraph("<h3>--- Raw Evaluation Metrics ---</h3>", styles['h3']))

    Story.append(Paragraph(
        f"<b>Compilation Status:</b> {report_data.get('compile_info', {}).get('status')}",
        styles['Normal']
    ))

    test_info = report_data.get('test_info', {})
    Story.append(Paragraph(
        f"<b>Functional Tests:</b> {test_info.get('passed_count', 0)} / {test_info.get('total_count', 0)} Passed",
        styles['Normal']
    ))
    Story.append(Paragraph(
        f"<b>Test Repair Attempted:</b> {test_info.get('repaired_attempted', False)}",
        styles['Normal']
    ))

    Story.append(Paragraph(
        f"<b>Initial Calculated Score:</b> {report_data.get('final_score', 0.0):.2f}",
        styles['Normal']
    ))

    Story.append(Spacer(1, 12))
    doc.build(Story)
    buffer.seek(0)
    return buffer


# ---------------------------------------------------------------------
# STREAMLIT UI LOGIC (UNCHANGED)
# ---------------------------------------------------------------------

st.title("🎓 C Autograder: Fully Agentic LangGraph Pipeline")

st.caption(
    "The agent uses conditional logic for routing:\n"
    "- If compilation fails, a failure report is generated.\n"
    "- If 0/N tests pass, a Test Repair Agent is invoked.\n"
    "- Final review is done by Gemini 2.5 Flash with detailed feedback."
)

default_code = """#include <stdio.h>
int main() {
    int a, b;
    printf("Enter two numbers\\n");
    if (scanf("%d %d", &a, &b) != 2) {
        return 1;
    }
    printf("%d", a + b);
    return 0;
}
"""

col1, col2 = st.columns([2, 1])

with col1:
    uploaded_file = st.file_uploader("Upload C Source Code (.c file)", type="c")
    st.markdown("---")
    user_code = st.text_area(
        "OR Paste C Source Code here (`main` function only)",
        default_code,
        height=300,
        key="code_input"
    )

with col2:
    st.header("Pipeline Control")
    st.info("The agent dynamically chooses its next step.")
    run_button = st.button("🚀 Run Agentic Autograder", type="primary", key="run_button")

if run_button:
    if uploaded_file is not None:
        code_to_grade = uploaded_file.getvalue().decode("utf-8")
    elif user_code and user_code != default_code:
        code_to_grade = user_code
    else:
        st.error("Please provide C code.")
        st.stop()

    with st.spinner("Running Agentic Pipeline..."):
        results = run_grader_pipeline(code_to_grade)

if 'results' in st.session_state and st.session_state.results:
    results = st.session_state.results
    final_report_data = results.get('final_report', {})

    st.markdown("---")
    col_score, col_download = st.columns([3, 1])

    final_score = results.get('final_score', 0.0)
    col_score.metric("Final Agentic Score", f"{final_score * 100:.1f} / 100")

    pdf_buffer = build_pdf(results)
    col_download.download_button(
        label="Download A4 PDF Report",
        data=pdf_buffer,
        file_name="C_Autograder_Report.pdf",
        mime="application/pdf"
    )

    st.markdown("---")
    st.header("Agent Feedback Report (Generated by Gemini 2.5 Flash)")

    if final_report_data:
        st.subheader(final_report_data.get('summary', 'No Summary.'))
        st.markdown(final_report_data.get('detailed_feedback', ''), unsafe_allow_html=True)

    st.markdown("---")
    st.header("Raw Evaluation Data (Diagnostics)")

    # ✅ BULLET-STYLE DIAGNOSTICS (NO JSON)

    with st.expander("Compilation Info"):
        c = results.get('compile_info', {})
        st.markdown(f"""
• Status: {c.get('status')}
• Errors:
{c.get('stderr', 'None')}
""")

    with st.expander("Test Cases Used"):
        for t in results.get('test_cases_used', []):
            st.markdown(f"• Input: `{t['input']}` → Expected: `{t['expected_output']}`")

    with st.expander("Test Results"):
        ti = results.get('test_info', {})
        for t in ti.get('test_results', []):
            st.markdown(
                f"• Input: `{t['input']}` | Expected: `{t['expected']}` | Actual: `{t['actual']}` | Passed: {t['passed']}"
            )

    with st.expander("Static Analysis Info"):
        for issue in results.get('static_info', {}).get('issues', []):
            st.markdown(f"• {issue}")

    with st.expander("Performance Info"):
        p = results.get('perf_info', {})
        st.markdown(f"""
• Execution Time: {p.get('execution_time_ms')} ms  
• Memory Used: {p.get('memory_kb')} KB
""")
