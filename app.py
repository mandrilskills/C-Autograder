import streamlit as st
import asyncio
from grader_langgraph import build_grader_graph, feedback

# Build the LangGraph once
g = build_grader_graph()

st.set_page_config(page_title="C Code AutoGrader", layout="wide")

# ====== PAGE TITLE ======
st.title("🧠 Agentic C Code AutoGrader with Test Evaluation")

st.markdown("""
Upload or paste your **C program**.  
The system will:
1. Compile your code  
2. Run functional test cases  
3. Perform static analysis (via cppcheck)  
4. Measure performance  
and finally display results on the right panel.
""")

# ====== LAYOUT ======
col1, col2 = st.columns([1, 1.2])

with col1:
    st.header("💻 Code Input")
    uploaded_file = st.file_uploader("📂 Upload a C file", type=["c"])
    code_input = st.text_area("📝 Or paste your C code here:", height=250)

    if uploaded_file:
        code = uploaded_file.read().decode("utf-8")
    elif code_input.strip():
        code = code_input.strip()
    else:
        code = ""

    # Example test cases
    st.header("🧪 Test Cases")
    st.caption("You can modify or add sample input-output pairs.")
    default_tests = [
        {"input": "2 3\n", "output": "5"},
        {"input": "10 20\n", "output": "30"},
    ]

    test_data = st.text_area(
        "Enter test cases (input=>expected_output format, one per line):",
        value="\n".join(f"{t['input'].strip()} => {t['output']}" for t in default_tests),
        height=100,
    )

    # Parse test cases
    tests = []
    for line in test_data.splitlines():
        if "=>" in line:
            inp, out = line.split("=>", 1)
            tests.append({"input": inp.strip() + "\n", "output": out.strip()})

    submission_id = "user1"

# ====== ASYNC EXECUTION ======
async def run_graph():
    inputs = {}
    config_payload = {
        "configurable": {
            "submission_id": submission_id,
            "source_code": code,
            "tests": tests,
        }
    }
    return await g.ainvoke(inputs, config=config_payload)

# ====== RUN BUTTON ======
with col1:
    if st.button("🚀 Run Autograder", type="primary"):
        if not code.strip():
            st.warning("Please upload or paste a C program first.")
        else:
            with st.spinner("Evaluating your code... ⏳"):
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    results = loop.run_until_complete(run_graph())
                    fb = feedback(results)

                    st.session_state["results"] = fb
                    st.session_state["raw_state"] = results
                    st.success("✅ Evaluation completed successfully!")

                except Exception as e:
                    st.error(f"Error while running graph: {e}")

# ====== RESULT PANEL ======
with col2:
    if "results" in st.session_state:
        fb = st.session_state["results"]
        raw = st.session_state["raw_state"]

        st.header("📊 Evaluation Report")
        st.markdown(f"**Final Score:** {fb['final_score']}%")

        for section in fb["sections"]:
            st.markdown(f"### 🧩 {section['section']}")
            st.progress(section["score"] / 100)
            st.code(section["text"], language="text")

        # Show detailed test results
        if "test" in raw and raw["test"].get("results"):
            st.subheader("🧾 Detailed Test Results")
            for idx, t in enumerate(raw["test"]["results"], 1):
                st.markdown(
                    f"**Test {idx}:** {'✅ Passed' if t['passed'] else '❌ Failed'}\n\n"
                    f"**Input:** `{t['input'].strip()}`  \n"
                    f"**Expected:** `{t['expected']}`  \n"
                    f"**Output:** `{t['output']}`"
                )
                st.divider()

        st.markdown(f"### 🏁 Conclusion\n{fb['conclusion']}")
    else:
        st.info("Run the autograder to see the evaluation report here.")
