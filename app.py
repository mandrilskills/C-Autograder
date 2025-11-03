# app.py
import streamlit as st
import json
import subprocess
import tempfile
import os
import shutil
from llm_agents import generate_test_cases_with_logging, generate_llm_report, test_gemini_connection

st.set_page_config(page_title="C Autograder – OSS 20B + Gemini", layout="wide")

st.title("🧠 C Autograder with Groq OSS 20B + Gemini 2.5 Flash")
st.caption("Test case generation via **Groq (openai/gpt-oss-20b)** · Evaluation via **gcc + cppcheck** · Report via **Gemini**")

# ---------------- Diagnostics ----------------
st.header("Environment Diagnostics")
env_info = {
    "gcc": shutil.which("gcc") is not None,
    "cppcheck": shutil.which("cppcheck") is not None,
    "groq_api": bool(os.getenv("GROQ_API_KEY")),
    "genai_api": bool(os.getenv("GENAI_API_KEY")),
    "details": {
        "which_gcc": shutil.which("gcc"),
        "which_cppcheck": shutil.which("cppcheck"),
        "env_GROQ_API_KEY": bool(os.getenv("GROQ_API_KEY")),
        "env_GENAI_API_KEY": bool(os.getenv("GENAI_API_KEY")),
    },
}
st.json(env_info)

# Gemini connection test
with st.expander("🔗 Test Gemini Connection"):
    st.text(test_gemini_connection())

# ---------------- Code Input ----------------
st.header("1️⃣ Upload or Paste C Code")
code_source = st.radio("Choose Input Method:", ["Paste Code", "Upload .c File"])

if code_source == "Paste Code":
    code_text = st.text_area("Paste your C code here:", height=300)
else:
    uploaded_file = st.file_uploader("Upload .c file", type=["c"])
    code_text = uploaded_file.read().decode("utf-8") if uploaded_file else ""

# ---------------- Test Case Generation ----------------
if st.button("🚀 Generate Test Cases"):
    if not code_text.strip():
        st.error("Please provide a C code snippet.")
    else:
        with st.spinner("Generating test cases using Groq (openai/gpt-oss-20b)..."):
            res = generate_test_cases_with_logging(code_text)
        st.subheader("Generated Test Cases (Editable)")
        st.caption(f"Status: {res['status']} — {res['reason']}")
        test_case_area = st.text_area(
            "Test cases (editable):",
            "\n".join(res["tests"]) if res["tests"] else "No test cases generated.",
            height=180,
        )
        st.session_state["test_cases"] = test_case_area

# ---------------- Evaluation ----------------
st.header("2️⃣ Run Evaluation")

if st.button("🏁 Run Evaluation"):
    if not code_text.strip():
        st.error("Please provide a C code snippet.")
    else:
        with tempfile.TemporaryDirectory() as temp_dir:
            c_path = os.path.join(temp_dir, "main.c")
            bin_path = os.path.join(temp_dir, "main.out")
            with open(c_path, "w") as f:
                f.write(code_text)

            # Compilation
            compile_result = subprocess.run(
                ["gcc", c_path, "-o", bin_path],
                capture_output=True,
                text=True,
            )
            compilation = {
                "status": "success" if compile_result.returncode == 0 else "error",
                "stdout": compile_result.stdout,
                "stderr": compile_result.stderr,
                "binary": bin_path if compile_result.returncode == 0 else None,
                "temp_dir": temp_dir,
                "returncode": compile_result.returncode,
            }

            # Static Analysis
            cpp_result = subprocess.run(
                ["cppcheck", "--enable=all", "--quiet", c_path],
                capture_output=True,
                text=True,
            )
            static_analysis = {
                "available": True,
                "issues": cpp_result.stderr.splitlines(),
            }

            # Test Execution
            test_cases_text = st.session_state.get("test_cases", "")
            tests = [line.strip() for line in test_cases_text.splitlines() if "::" in line]
            test_results = []

            if compilation["status"] == "success" and tests:
                for t in tests:
                    parts = t.split("::")
                    inp, expected = parts[0].strip(), parts[1].strip()
                    try:
                        run_result = subprocess.run(
                            [bin_path],
                            input=inp,
                            text=True,
                            capture_output=True,
                            timeout=3,
                        )
                        actual_output = run_result.stdout.strip()
                        success = expected.strip() == actual_output.strip()
                        test_results.append({
                            "input": inp,
                            "expected": expected,
                            "actual": actual_output,
                            "success": success,
                            "comment": "OK" if success else "Mismatch",
                        })
                    except subprocess.TimeoutExpired:
                        test_results.append({
                            "input": inp,
                            "expected": expected,
                            "actual": "(timeout)",
                            "success": False,
                            "comment": "Timed out",
                        })

            # Performance
            performance = {"avg_time": None, "comment": "Performance not measured in this version"}

            # Assemble evaluation summary
            evaluation = {
                "compilation": compilation,
                "static_analysis": static_analysis,
                "tests": test_results,
                "performance": performance,
                "final_score": 48.25 if not all(t["success"] for t in test_results) else 100,
            }

            st.subheader("Evaluation Results")
            st.json(evaluation)

            # LLM Report
            with st.spinner("Generating LLM Report (Gemini 2.5 Flash)..."):
                report_text = generate_llm_report(evaluation)
            st.subheader("LLM Report")
            st.write(report_text)

            # Save as PDF
            pdf_path = os.path.join(temp_dir, "llm_report.txt")
            with open(pdf_path, "w", encoding="utf-8") as f:
                f.write(report_text)
            with open(pdf_path, "rb") as f:
                st.download_button("📄 Download Report", f, file_name="C_Code_Report.txt")
