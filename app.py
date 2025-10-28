import streamlit as st
from grader_langgraph import build_grader_graph, feedback

st.set_page_config(page_title="C Code AutoGrader", layout="wide")
st.title("💻 C Code AutoGrader (Agentic System)")

st.markdown("### Upload your C file or paste your code below:")

uploaded_file = st.file_uploader("Upload `.c` file", type=["c"])
code_input = st.text_area("Or paste your C code here:", height=250)

if uploaded_file:
    source_code = uploaded_file.read().decode("utf-8")
else:
    source_code = code_input

st.markdown("### 🧩 Test Cases")
test_input = st.text_area(
    "Enter test cases (input => expected_output):",
    "2 3 => 5\n10 20 => 30",
    height=100
)

tests = []
for line in test_input.strip().splitlines():
    if "=>" in line:
        i, o = line.split("=>")
        tests.append({"input": i.strip(), "output": o.strip()})

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
            # ✅ synchronous invoke, no async issues
            result = g.invoke(inputs, config=config)
            return result

        result = run_graph()
        fb = feedback(result)

        st.success("✅ Evaluation completed successfully!")

        st.subheader("📊 Evaluation Report")
        st.markdown(f"**Final Score:** {fb['final_score']}%")

        for sec in fb["sections"]:
            st.markdown(f"### 🧠 {sec['section']}")
            st.markdown(f"**Score:** {sec['score']}%")
            st.code(sec["text"], language="text")

        st.markdown("### 🏁 Conclusion")
        st.info(fb["conclusion"])
