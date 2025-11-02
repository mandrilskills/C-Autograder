import streamlit as st
import subprocess
import os
import json
from llm_agents import (
    generate_test_cases,
    fallback_code_evaluation,
    generate_detailed_report,
    create_pdf_report
)

# ----------------- Streamlit UI Setup ----------------- #
st.set_page_config(page_title="AI C Autograder", layout="wide")
st.title("🤖 AI-Powered C Autograder (Gemini + LangGraph)")

st.markdown(
    """
This tool uses **Google Gemini (via LangChain)** to:
1. Automatically generate **test cases** for your C program  
2. Compile and run it against those test cases  
3. Create a **detailed report** with performance feedback  
4. If test cases can’t be generated, perform **AI-based static evaluation**
"""
)

uploaded_file = st.file_uploader("📂 Upload your `.c` file for grading", type=["c"])

if uploaded_file is not None:
    code_text = uploaded_file.read().decode("utf-8")
    st.code(code_text, language="c")

    # Step 1: Generate test cases (with spinner)
    with st.spinner("🧠 Generating test cases using Gemini..."):
        test_cases = generate_test_cases(code_text)

    if test_cases:
        st.success("✅ Test cases generated successfully.")
        st.write("### 🧩 Generated Test Cases")
        st.json(test_cases)

        # Step 2: Compile and run the C program
        with open("submitted_code.c", "w") as f:
            f.write(code_text)

        st.info("⚙️ Compiling and testing program...")

        try:
            compile_result = subprocess.run(
                ["gcc", "submitted_code.c", "-o", "program"],
                capture_output=True,
                text=True,
            )

            if compile_result.returncode != 0:
                st.error("❌ Compilation failed:")
                st.text(compile_result.stderr)
                report_text = f"Compilation Error:\n\n{compile_result.stderr}"
            else:
                st.success("✅ Compilation successful! Running test cases...")
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
                    except subprocess.TimeoutExpired:
                        results.append({
                            "input": case["input"],
                            "error": "Execution timed out",
                            "passed": False
                        })
                    except Exception as e:
                        results.append({
                            "input": case["input"],
                            "error": str(e),
                            "passed": False
                        })

                st.write("### 🧾 Test Case Results")
                st.json(results)

                # Step 3: Generate detailed report
                with st.spinner("📝 Generating performance report..."):
                    report_text = generate_detailed_report(code_text, results)

        except Exception as e:
            st.error(f"Runtime error: {e}")
            report_text = f"Runtime error occurred: {e}"

    else:
        # ------------------ Fallback System ------------------ #
        st.warning("⚠️ Unable to generate valid test cases. Switching to AI static evaluation.")
        with st.spinner("🧩 Performing static analysis via Gemini..."):
            report_text = fallback_code_evaluation(code_text)

    # Step 4: Show report (whether from test results or fallback)
    if report_text:
        st.subheader("📘 Final Report")
        st.text_area("Gemini Evaluation Report", report_text, height=400)

        # Step 5: PDF Download Option
        with st.spinner("📄 Preparing downloadable report..."):
            pdf_path = create_pdf_report(report_text)

        with open(pdf_path, "rb") as f:
            st.download_button(
                label="📥 Download Report as PDF",
                data=f,
                file_name="grading_report.pdf",
                mime="application/pdf",
            )

# ------------------ Footer ------------------ #
st.markdown("---")
st.caption("🔹 Developed with LangChain, Gemini 2.5 Flash, and Streamlit Cloud.")
