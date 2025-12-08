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
# The diagnostic function 'test_gemini_connection' has been removed from llm_agents.py 
# in the agentic restructure, so this import is removed to fix the ImportError.
# from llm_agents import test_gemini_connection # <--- REMOVED

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
    
    formatted_feedback = feedback_text.replace('\n', '<br/>')
    Story.append(Paragraph(formatted_feedback, styles['Normal']))
    
    # ... (rest of the PDF generation details) ...
    
    doc.build(Story)
    buffer.seek(0)
    return buffer


# ---------------------------------------------------------------------
# STREAMLIT UI LOGIC
# ---------------------------------------------------------------------

st.title(" 🎓 C Autograder: Fully Agentic LangGraph Pipeline")
st.caption("Dynamic routing handles critical errors (compilation failure) and attempts self-correction (Test Repair Agent).")

default_code = """#include <stdio.h>
int main() {
    int a, b;
    // CRITICAL: Missing a semicolon here to test the Decider Agent
    printf("Enter two numbers\\n")
    if (scanf("%d %d", &a, &b) != 2) {
        return 1;
    }
    printf("%d", a + b);
    return 0;
}
"""

col1, col2 = st.columns([2, 1])

with col1:
    user_code = st.text_area("C Source Code Submission (`main` function only)", default_code, height=400, key="code_input")

with col2:
    st.header("Pipeline Control")
    st.info("The agent uses conditional logic for routing: Compilation Failure -> Failure Report. 0/N Tests Passed -> Test Repair Agent -> Re-run Tests. All others follow the full path.")
    
    run_button = st.button("🚀 Run Agentic Autograder", type="primary", key="run_button")

# --- EXECUTION LOGIC ---
if run_button and user_code:
    st.session_state.results = None
    with st.spinner("Running Agentic Pipeline..."):
        try:
            results = run_grader_pipeline(user_code)
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
    
    # Download Button
    pdf_buffer = build_pdf(results)
    col_download.download_button(
        label="Download Full PDF Report",
        data=pdf_buffer,
        file_name="C_Autograder_Report.pdf",
        mime="application/pdf",
        type="secondary",
        use_container_width=True
    )

    st.markdown("---")
    
    # Display LLM Report
    st.header("Agent Feedback Report")
    
    if final_report_data:
        st.subheader(final_report_data.get('summary', 'No Summary.'))
        # Use HTML for rendering the feedback which contains section breaks (<br/>)
        st.markdown(final_report_data.get('detailed_feedback', 'Detailed feedback is missing.'), unsafe_allow_html=True)
    else:
        st.warning("The Final Reviewer Agent failed to generate a report.")
        
    st.markdown("---")

    # Display Raw Data Tabs
    st.header("Raw Evaluation Data")
    tabs = st.tabs(["Compilation", "Testing/Functional", "Static Analysis", "Performance", "Full State"])
    
    # Placeholder for displaying raw data in tabs
    
    with tabs[0]:
        st.json(results.get('compile_info'))
    with tabs[1]:
        st.json(results.get('test_info'))
        st.caption("Test Cases Used:")
        st.json(results.get('test_cases_used'))
    with tabs[2]:
        st.json(results.get('static_info'))
    with tabs[3]:
        st.json(results.get('perf_info'))
    with tabs[4]:
        # Exclude the large 'final_report' data to keep the raw state cleaner
        full_state_copy = {k: v for k, v in results.items() if k != 'final_report'}
        st.json(full_state_copy)
