import streamlit as st
import os
import subprocess
import json
from llm_agents import (
    generate_test_cases,
    fallback_code_evaluation,
    generate_detailed_report,
    create_pdf_report
)

# ---------- Streamlit UI ---------- #
st.set_page_config(page_title="AI C Autograder", layout="wide")
st.title("🤖 AI-Powered C Autograder with Gemini & LangGraph")

uploaded_file = st.file_uploader("📂 Upload your C file", type=["c"])

if uploaded_file is not None:
    code_text = uploaded_file.read().decode("utf-8")
    st.code(code_text, language="c")

    # Step 1: Generate test cases
    test_cases = generate_test_cases(code_text)

    if test_cases:
        st.write("### 🧩 Generated Test Cases")
        st.json(test_cases)

        # Step 2: Run the uploaded C program
        with open("submitted_code.c", "w") as f:
            f.write(code_text)

        try:
            # Compile the C code
            compile_result = subprocess.run(
                ["gcc", "submitted_code.c", "-o", "program"],
                capture_output=True,
                text=True
            )

            if compile_result.returncode != 0:
                st.error("❌ Compilation failed:")
                st.text(compile_result.stderr)
            else:
                # Execute each test case
                results = []
                for case in test_cases:
                    try:
                        process = subprocess.run(
                            ["./program"],
                            input=case["input"],
                            text=True,
                            capture_output=True,
                            timeout=3
                        )
                        results.append({
                            "input": case["input"],
                            "expected_output": case["expected_output"],
                            "actual_output": process.stdout.strip(),
                            "passed": process.stdout.strip() == case["expected_output"].strip()
                        })
                    except Exception as e:
                        results.append({
                            "input": case["input"],
                            "error": str(e),
                            "passed": False
                        })

                st.write("### 🧾 Test Case Results")
                st.json(results)

                # Step 3: Generate final report
                report_text = generate_detailed_report(code_text, results)

        except Exception as e:
            st.error(f"Runtime error: {e}")

    else:
        # Fallback: qualitative analysis
        st.warning("⚠️ No valid test cases generated. Running static evaluation instead.")
        report_text = fallback_code_evaluation(code_text)

    # Step 4: Display Report
    if report_text:
        st.subheader("📘 Final Report")
        st.text_area("Report Summary", report_text, height=400)

        # Step 5: PDF Download
        pdf_path = create_pdf_report(report_text)
        with open(pdf_path, "rb") as f:
            st.download_button(
                label="📥 Download Report as PDF",
                data=f,
                file_name="grading_report.pdf",
                mime="application/pdf"
            )
