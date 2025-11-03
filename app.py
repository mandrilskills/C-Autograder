import streamlit as st
import subprocess
import os
import json
from llm_agents import (
    generate_test_cases,
    fallback_code_evaluation,
    generate_detailed_report,
    create_pdf_report,
)

# ---------------- Streamlit Page Setup ---------------- #
st.set_page_config(page_title="AI C Autograder (Gemini 2.5 Flash)", layout="wide")
st.title("🤖 AI-Powered C Autograder – Gemini 2.5 Flash Edition")

st.markdown(
    """
### 🧠 Features
1. Auto-generate **test cases** for your C code  
2. Compile & run it against those cases  
3. Create a **detailed Gemini report** 4. If no test cases can be generated → perform **static evaluation**
"""
)

# ---------------- Gemini Connection Test ---------------- #
if st.button("🔍 Test Gemini 2.5 Flash Connection"):
    import google.generativeai as genai

    try:
        # Note: In the Canvas environment, the API key is automatically handled.
        # We ensure the model is configured for a quick test.
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel("gemini-2.5-flash")
        resp = model.generate_content("Say 'Gemini 2.5 Flash connected successfully!'")
        st.success(resp.text)
    except Exception as e:
        st.error(f"Connection failed: {e}")

st.divider()

# ---------------- File Upload ---------------- #
uploaded_file = st.file_uploader("📂 Upload your C file", type=["c"])

if uploaded_file:
    code_text = uploaded_file.read().decode("utf-8")
    st.code(code_text, language="c")

    with st.spinner("🧠 Generating test cases using Gemini 2.5 Flash..."):
        test_cases = generate_test_cases(code_text)

    # ---------- Case 1 – Normal test-based flow (Actual Execution) ---------- #
    if test_cases:
        st.success("✅ Test cases generated successfully.")
        st.json(test_cases)

        with open("submitted_code.c", "w") as f:
            f.write(code_text)

        st.info("⚙️ Compiling and testing program...")

        try:
            # --- Compilation ---
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
                
                # --- Execution ---
                for case in test_cases:
                    expected_output = case["expected_output"].strip()
                    
                    try:
                        process = subprocess.run(
                            ["./program"],
                            input=case["input"],
                            text=True,
                            capture_output=True,
                            timeout=3,
                        )
                        
                        actual_output = process.stdout.strip()
                        # Use string 'PASS'/'FAIL' for consistency with LLM reporting
                        result_status = "PASS" if actual_output == expected_output else "FAIL"
                        
                        results.append(
                            {
                                "input": case["input"],
                                "expected_output": expected_output,
                                "actual_output": actual_output,
                                "result": result_status,
                            }
                        )
                        
                    except subprocess.TimeoutExpired:
                        results.append(
                            {
                                "input": case["input"],
                                "expected_output": expected_output,
                                "actual_output": "TIMED OUT",
                                "result": "FAIL",
                            }
                        )
                    except Exception as e:
                        results.append(
                            {
                                "input": case["input"],
                                "expected_output": expected_output,
                                "actual_output": f"RUNTIME ERROR: {str(e)}",
                                "result": "FAIL",
                            }
                        )
                
                # --- Display Results ---
                st.write("### 🧾 Test Case Results")
                
                # Calculate passes/fails using the consistent 'result' key
                passes = sum(1 for r in results if r.get('result') == 'PASS')
                st.info(f"Summary: **{passes}/{len(results)} tests passed.**")
                
                st.json(results)

                with st.spinner("📝 Generating performance report..."):
                    # Pass the results (now correctly formatted with 'result': 'PASS'|'FAIL')
                    report_text = generate_detailed_report(code_text, results)

        except Exception as e:
            st.error(f"Runtime error: {e}")
            report_text = f"Runtime error: {e}"

    # ---------- Case 2 – Fallback Static Evaluation ---------- #
    else:
        st.warning("⚠️ Unable to generate valid test cases. Switching to AI Static Evaluation Mode.")
        with st.spinner("🧩 Performing static analysis..."):
            report_text = fallback_code_evaluation(code_text)

    # ---------- Final Report and Download ---------- #
    if 'report_text' in locals() and report_text:
        st.subheader("📘 Final Report")
        st.text_area("Gemini Evaluation Report", report_text, height=400)

        with st.spinner("📄 Preparing downloadable report..."):
            pdf_buf = create_pdf_report(report_text)

        st.download_button(
            label="📥 Download Report as PDF",
            data=pdf_buf,
            file_name="grading_report.pdf",
            mime="application/pdf",
        )

st.divider()
st.caption("🔹 Built with Streamlit · Gemini 2.5 Flash")

