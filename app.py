# App.py

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
# PAGE CONFIGURATION AND STYLING
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="C Autograder | Fully Agentic LangGraph",
    layout="wide",
    page_icon=" 🎓 "
)
# (Styling markdown block remains the same)
# ...

# ---------------------------------------------------------------------
# PDF REPORT GENERATION
# ---------------------------------------------------------------------

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
    
    # Preserve formatting for detailed feedback
    formatted_feedback = feedback_text.replace('\n', '<br/>')
    Story.append(Paragraph(formatted_feedback, styles['Normal']))
    
    # Append Raw Data (optional but helpful for a detailed report)
    Story.append(Spacer(1, 24))
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
    
    # Build the PDF
    doc.build(Story)
    buffer.seek(0)
    return buffer


# ---------------------------------------------------------------------
# STREAMLIT UI LOGIC
# ---------------------------------------------------------------------

st.title(" 🎓 C Autograder: Fully Agentic LangGraph Pipeline")
st.caption("The agent uses conditional logic for routing: Compilation Failure → Failure Report. 0/N Tests Passed → Test Repair Agent (Groq) → Re-run Tests. Final review is by Gemini 2.5 Flash.")

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
    # 1. ADD FILE UPLOAD OPTION
    uploaded_file = st.file_uploader("Upload C Source Code (.c file)", type="c")
    st.markdown("---")
    user_code = st.text_area("OR Paste C Source Code here (`main` function only)", default_code, height=300, key="code_input")

with col2:
    st.header("Pipeline Control")
    st.info("The agent dynamically chooses its next step based on the outcome of the previous step, demonstrating true agentic behavior.")
    
    run_button = st.button("🚀 Run Agentic Autograder", type="primary", key="run_button", use_container_width=True)

# --- EXECUTION LOGIC ---
if run_button:
    
    code_to_grade = ""
    # Prioritize uploaded file
    if uploaded_file is not None:
        code_to_grade = uploaded_file.getvalue().decode("utf-8")
        st.success(f"Grading file: {uploaded_file.name}")
    elif user_code and user_code != default_code: # Use text area if content is provided
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

# --- DISPLAY RESULTS ---
if 'results' in st.session_state and st.session_state.results:
    results = st.session_state.results
    final_report_data = results.get('final_report', {})
    
    st.markdown("---")
    
    col_score, col_download = st.columns([3, 1])

    # Display Final Score
    final_score = results.get('final_score', 0.0)
    col_score.markdown(f"""
        <div style="padding: 15px; border-radius: 10px; background-color: #1a1a2e; border: 2px solid #6ecbff;">
            <h3 style="color: #fff; margin-top: 0;">FINAL AGENTIC SCORE</h3>
            <h1 style="color: #a8dadc; font-size: 4em; margin-bottom: 0;">{final_score * 100:.1f} / 100</h1>
        </div>
    """, unsafe_allow_html=True)
    
    # 4. DOWNLOAD OPTION (A4 PDF)
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
    
    # 3. DETAILED REPORT BY GEMINI
    st.header("Agent Feedback Report (Generated by Gemini 2.5 Flash)")
    
    if final_report_data:
        st.subheader(final_report_data.get('summary', 'No Summary.'))
        # Use HTML for rendering the feedback which contains section breaks (<br/>)
        st.markdown(final_report_data.get('detailed_feedback', 'Detailed feedback is missing.'), unsafe_allow_html=True)
    else:
        st.warning("The Final Reviewer Agent failed to generate a report.")
        
    st.markdown("---")

    # Display Raw Data Tabs (for diagnostic use)
    st.header("Raw Evaluation Data (Diagnostics)")
    tabs = st.tabs(["Compilation", "Testing/Functional", "Static Analysis", "Performance", "Full State"])
    
    with tabs[0]:
        st.json(results.get('compile_info'))
    with tabs[1]:
        # 2. GROQ GENERATED TEST CASES
        st.caption("Test Cases Used (Generated by Groq Agent):")
        st.json(results.get('test_cases_used'))
        st.caption("Test Results:")
        st.json(results.get('test_info'))
    with tabs[2]:
        st.json(results.get('static_info'))
    with tabs[3]:
        st.json(results.get('perf_info'))
    with tabs[4]:
        # Exclude the large 'final_report' data to keep the raw state cleaner
        full_state_copy = {k: v for k, v in results.items() if k != 'final_report'}
        st.json(full_state_copy)
