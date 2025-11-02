import streamlit as st
from grader_langgraph import build_grader_graph, feedback
from llm_agents import generate_test_cases, generate_detailed_report, create_pdf_report
import json

st.set_page_config(page_title="C Code AutoGrader", layout="wide")
st.title("💻 C Code AutoGrader (Agentic System + Gemini 2.5 Flash Integration)")

st.markdown("### Upload your C file or paste your code below:")

uploaded_file = st.file_uploader("Upload `.c` file", type=["c"])
code_input = st.text_area("Or paste your C code here:", height=250)

if uploaded_file:
    source_code = uploaded_file.read().decode("utf-8")
else:
    source_code = code_input

# === Test Case Section ===
st.markdown("### 🧩 Test Cases")

auto_gen = st.button("🤖 Generate Test Cases Automatically")
tests = []

if auto_gen and source_code.strip():
    st.info("Generating test cases using Gemini 2.5 Flash... ⏳")
    try:
        raw = generate_test_cases(source_code)
        tests = json.loads(raw)
        st.success("✅ AI-generated test cases:")
        for t in tests:
            st.code(f"{t['input']} => {t['expected_output']}")
    except Exception as e:
        st.error(f"Error generating test cases: {e}")
else:
    test_input = st.text_area(
        "Or manually enter test cases (input => expected_output):",
        "2 3 => 5\n10 20 => 30",
        height=100
    )
    for line in test_input.strip().splitlines():
        if "=>" in line:
            i, o = line.split("=>")
            tests.append({"input": i.strip(), "output": o.strip()})

# === Run Autograder ===
if st.button("🚀 Run Autograder"):
    if not source_code.strip():
        st.error("Please provide C code first.")
    else:
        st.info("Running evaluation... Please wait ⏳")

        def run_graph():
            g = build_grader_graph()
            inputs = {}
            config = {
                "configurable": {
                    "submission_id": "user1",
                    "source_code": source_code,
                    "tests": tests
                }
            }
            result = g.invoke(inputs, config=config)
            return result

        result = run_graph()
        fb = feedback(result)

        st.success("✅ Evaluation completed successfully!")

        # === Display Report ===
        st.subheader("📊 Evaluation Report")
        st.markdown(f"**Final Score:** {fb['final_score']}%")

        for sec in fb["sections"]:
            st.markdown(f"### 🧠 {sec['section']}")
            st.markdown(f"**Score:** {sec['score']}%")
            st.code(sec["text"], language="text")

        st.markdown("### 🏁 Conclusion")
        st.info(fb["conclusion"])

        # === Generate AI Report with Gemini 2.5 Flash ===
        st.info("Generating detailed AI report using Gemini 2.5 Flash... ⏳")
        ai_report = generate_detailed_report(fb)

        st.subheader("📝 Detailed AI Report")
        st.write(ai_report)

        # === Create PDF ===
        pdf_bytes = create_pdf_report(fb, ai_report)
        st.download_button(
            label="📥 Download PDF Report",
            data=pdf_bytes,
            file_name="AI_Grading_Report.pdf",
            mime="application/pdf"
        )
