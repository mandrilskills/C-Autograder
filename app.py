import streamlit as st
import asyncio
from grader_langgraph import build_grader_graph, feedback

# Build the LangGraph once
g = build_grader_graph()

st.set_page_config(page_title="C Code AutoGrader", layout="wide")

st.title("🧠 Agentic C Code AutoGrader (LangGraph + Streamlit)")

st.markdown("""
Upload a **C source file (.c)** or paste your code below.
The system will compile, run static analysis, and evaluate performance automatically.
""")

# ========== INPUT SECTION ==========
uploaded_file = st.file_uploader("📂 Upload a C file", type=["c"])
code_input = st.text_area("📝 Or paste your C code here:", height=250)

if uploaded_file:
    code = uploaded_file.read().decode("utf-8")
elif code_input.strip():
    code = code_input.strip()
else:
    code = ""

submission_id = "user1"

# ========== EXECUTION ==========
async def run_graph():
    inputs = {}
    config_payload = {
        "configurable": {
            "submission_id": submission_id,
            "source_code": code,
        }
    }
    return await g.ainvoke(inputs, config=config_payload)

if st.button("🚀 Run Autograder", type="primary"):
    if not code.strip():
        st.warning("Please upload or paste a C program first.")
    else:
        with st.spinner("Evaluating your code... Please wait ⏳"):
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                results = loop.run_until_complete(run_graph())
                fb = feedback(results)

                st.success("✅ Evaluation completed successfully!")

                st.subheader("📊 Evaluation Report")
                st.markdown(f"**Final Score:** {fb['final_score']}%")

                for section in fb["sections"]:
                    st.markdown(f"### 🧩 {section['section']}")
                    st.progress(section["score"] / 100)
                    st.code(section["text"], language="text")

                st.markdown(f"### 🏁 Conclusion\n{fb['conclusion']}")

            except Exception as e:
                st.error(f"Error while running graph: {e}")
