import streamlit as st
import os
import json
from llm_agents import (
    generate_test_cases,
    generate_detailed_report,
    create_pdf_report,
)
from grader_langgraph import run_grader_pipeline
from typing import Dict, List

# ---------------- Streamlit Page Setup ---------------- #
st.set_page_config(page_title="AI C Autograder (Execution & Analysis)", layout="wide")
st.title("🤖 AI-Powered C Autograder")
st.caption("Execution powered by GCC/CppCheck and coordinated by LangGraph Agents. Reporting by Gemini 2.5 Flash.")

st.markdown(
    """
### 🧠 Analysis Workflow
1.  **Test Cases (Gemini):** Generates structured test cases (`input`/`output`).
2.  **Execution (LangGraph):** Compiles code, runs tests, performs static analysis, and checks performance.
3.  **Final Report (Gemini):** Synthesizes all execution and analysis data into a detailed, human-readable report.
"""
)
st.divider()

# ---------------- Step 1: Code Input (Upload or Write) ---------------- #
code_text = ""
st.subheader("1. Provide Your C Code")

tab1, tab2 = st.tabs(["📂 Upload C File", "✏️ Write/Paste Code"])

with tab1:
    uploaded_file = st.file_uploader("Upload your .c file", type=["c"])
    if uploaded_file:
        code_text = uploaded_file.read().decode("utf-8")
        st.code(code_text, language="c")

with tab2:
    pasted_code = st.text_area("Write or paste your C code here:", height=300, placeholder="#include <stdio.h>\n\nint main() {\n    // Your code here\n    return 0;\n}")
    if pasted_code:
        code_text = pasted_code

# ---------------- Main Analysis Button ---------------- #
st.divider()
if st.button("🚀 Run Full Analysis Pipeline", type="primary", use_container_width=True):
    if not code_text.strip():
        st.error("Please upload or write some C code to analyze.")
        st.stop()
    
    # ---------------- Step 2: Generate Test Cases (Gemini) ---------------- #
    st.subheader("2. Generated Test Cases")
    tests: List[Dict[str, str]] = []
    with st.spinner("🧠 Gemini is generating structured test cases..."):
        tests = generate_test_cases(code_text)
    
    if not tests:
        st.warning("⚠️ Could not generate structured test cases. Running static analysis only.")
    else:
        st.info(f"Generated {len(tests)} test cases for execution.")
        st.json(tests)

    st.divider()
    
    # ---------------- Step 3: Run Full Execution Pipeline (LangGraph) ---------------- #
    st.subheader("3. Execution & Static Analysis (LangGraph)")
    structured_results = {}
    
    with st.spinner("🤖 LangGraph agents are compiling, testing, and analyzing your code... (This will take a few moments)"):
        # Run the LangGraph execution and grading pipeline
        structured_results = run_grader_pipeline(code_text, tests)
        
    final_score = structured_results.get("final_score", 0.0)
    st.markdown(f"## **Final Overall Score: {final_score:.2f}%**")
    st.markdown(f"**Conclusion:** {structured_results.get('conclusion', 'Analysis complete.')}")
    
    st.write("---")
    st.markdown("### Detailed Section Scores")
    
    for section_data in structured_results.get("sections", []):
        score_pct = section_data.get("score", 0)
        st.markdown(f"#### **{section_data['section']}** ({score_pct:.1f}%)")
        st.code(section_data['text'], language='markdown')

    st.divider()

    # ---------------- Step 4: Final Report (Gemini) ---------------- #
    st.subheader("4. Final Detailed Report (from Gemini)")
    
    with st.spinner("📝 Gemini is writing the final, human-readable report with code suggestions..."):
        final_report = generate_detailed_report(code_text, structured_results)
        st.text_area("Gemini Evaluation Report", final_report, height=600)
            
        # ---------------- Step 5: PDF Download ---------------- #
        st.divider()
        st.subheader("5. Download Report")
        with st.spinner("📄 Preparing downloadable report..."):
            pdf_buf = create_pdf_report(final_report)

        st.download_button(
            label="📥 Download Full Report as PDF",
            data=pdf_buf,
            file_name="C_Code_Analysis_Report.pdf",
            mime="application/pdf",
            use_container_width=True
        )

st.divider()
st.caption("🔹 Built with Streamlit · Gemini 2.5 Flash · LangGraph")
