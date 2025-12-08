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

    # Title, Score, Summary
    Story.append(Paragraph("<h1>C Autograder Final Agentic Report</h1>", styles['h1']))
    Story.append(Spacer(1, 12))

    final_score = report_data.get('final_score', 'N/A')
    summary = report_data.get('final_report', {}).get('summary', 'No summary available.')

    Story.append(Paragraph(f"<h2>Final Score: {final_score:.2f} / 1.00</h2>", styles['h2']))
    Story.append(Paragraph(f"<b>Summary:</b> {summary}", styles['Normal']))
    Story.append(Spacer(1, 24))

    # Detailed Feedback (From LLM Agent)
    feedback_text = report_data.get('final_report', {}).get('detailed_feedback', 'Detailed feedback could not be retrieved.')
    Story.append(Paragraph("<h2>Detailed Agent Feedback (Gemini 2.5 Flash)</h2>", styles['h2']))
    formatted_feedback = feedback_text.replace('\n', '<br/>')
    Story.append(Paragraph(formatted_feedback, styles['Normal']))
    Story.append(Spacer(1, 24))

    # Append Raw Data (for detailed report)
    Story.append(Paragraph("<h3>--- Raw Evaluation Metrics ---</h3>", styles['h3']))
    # Compilation Info
    Story.append(Paragraph(f"<b>Compilation Status:</b> {report_data.get('compile_info', {}).get('status')}", styles['Normal']))

    # Test Info
    test_info = report_data.get('test_info', {})
    Story.append(Paragraph(f"<b>Functional Tests:</b> {test_info.get('passed_count', 0)} / {test_info.get('total_count', 0)} Passed", styles['Normal']))
    Story.append(Paragraph(f"<b>Test Repair Attempted:</b> {test_info.get('repaired_attempted', False)}", styles['Normal']))

    # Scoring
    Story.append(Paragraph(f"<b>Initial Calculated Score:</b> {report_data.get('final_score', 0.0):.2f}", styles['Normal']))
    Story.append(Spacer(1, 12))

    doc.build(Story)
    buffer.seek(0)
    return buffer

# ---------------------------------------------------------------------
# STREAMLIT UI LOGIC
# ---------------------------------------------------------------------
st.title("🎓 C Autograder: Fully Agentic LangGraph Pipeline")
st.caption("The agent uses conditional logic for routing:\n"
           "- If compilation fails, a failure report is generated.\n"
           "- If 0/N tests pass, a Test Repair Agent is invoked.\n"
           "- Final review is done by Gemini 2.5 Flash with detailed feedback.")

default_code = """#include <stdio.h>

int main() {

    int a, b;

    printf("Enter two numbers\\n"); // Note the semicolon is back to allow compilation

    if (scanf("%d %d", &a, &b) != 2) {

        return 1;

    }

    printf("%d", a + b);

    return 0;

}
"""

col1, col2 = st.columns([2, 1])

with col1:
    uploaded_file = st.file_uploader(
        "Upload C Source Code (.c file)", type="c",
        help="Upload a .c file containing your C code."
    )
    st.markdown("---")
    user_code = st.text_area(
        "OR Paste C Source Code here (`main` function only)", default_code,
        height=300, key="code_input",
        help="Paste your C code here. Provide only the main function."
    )

with col2:
    st.header("Pipeline Control")
    st.info("The agent dynamically chooses its next step based on the outcome of the previous step.")
    run_button = st.button(
        "🚀 Run Agentic Autograder", type="primary", key="run_button",
        help="Click to start the agentic autograder pipeline."
    )

if run_button:
    code_to_grade = ""
    if uploaded_file is not None:
        code_to_grade = uploaded_file.getvalue().decode("utf-8")
        st.success(f"Grading file: {uploaded_file.name}")
    elif user_code and user_code != default_code:
        code_to_grade = user_code
        st.success("Grading code from text area.")
    else:
        st.error("Please provide C code either by uploading a file or pasting it into the text area.")
        st.stop()

    st.session_state.results = None
    with st.spinner("Running Agentic Pipeline (Groq, Gemini, LangGraph)..."):
        try:
            results = run_grader_pipeline(code_to_grade)
            st.session_state.results = results
        except Exception as e:
            st.error(f"An unexpected error occurred during the pipeline run: {e}")
            logger.error(f"Pipeline error: {e}")

if 'results' in st.session_state and st.session_state.results:
    results = st.session_state.results
    final_report_data = results.get('final_report', {})

    st.markdown("---")
    col_score, col_download = st.columns([3, 1])

    # Display Final Score
    final_score = results.get('final_score', 0.0)
    col_score.metric("Final Agentic Score", f"{final_score * 100:.1f} / 100")

    # Download PDF Report
    pdf_buffer = build_pdf(results)
    col_download.download_button(
        label="Download A4 PDF Report",
        data=pdf_buffer,
        file_name="C_Autograder_Report.pdf",
        mime="application/pdf",
        type="secondary",
        use_container_width=True
    )

    st.markdown("---")
    st.header("Agent Feedback Report (Generated by Gemini 2.5 Flash)")

    if final_report_data:
        st.subheader(final_report_data.get('summary', 'No Summary.'))
        st.markdown(
            final_report_data.get('detailed_feedback', 'Detailed feedback is missing.'),
            unsafe_allow_html=True
        )
    else:
        st.warning("The Final Reviewer Agent failed to generate a report.")

    st.markdown("---")
    st.header("Raw Evaluation Data (Diagnostics)")

    with st.expander("Compilation Info"):
        st.json(results.get('compile_info'))

    with st.expander("Test Cases Used"):
        st.json(results.get('test_cases_used'))

    with st.expander("Test Results"):
        st.json(results.get('test_info'))

    with st.expander("Static Analysis Info"):
        st.json(results.get('static_info'))

    with st.expander("Performance Info"):
        st.json(results.get('perf_info'))

    with st.expander("Full State"):
        # Exclude the large 'final_report' for clarity
        full_state_copy = {k: v for k, v in results.items() if k != 'final_report'}
        st.json(full_state_copy)
