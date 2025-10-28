import asyncio
import time
import uuid
import json
import streamlit as st
from grader_langgraph import build_grader_graph, feedback

st.set_page_config(page_title="C Autograder", page_icon="💻", layout="wide")
st.title("💻 LangGraph C Autograder")

# Build/compile the graph once (build_grader_graph() returns a compiled graph)
g = build_grader_graph()

# --- Left column: input ---
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Provide your code")
    uploaded_file = st.file_uploader("Upload a .c file (optional)", type=["c"])
    if uploaded_file is not None:
        try:
            code = uploaded_file.read().decode("utf-8")
            st.success("✅ File loaded")
        except Exception as e:
            st.error(f"Could not read file: {e}")
            code = ""
    else:
        sample = """#include <stdio.h>
int main() {
    int a, b;
    scanf("%d %d", &a, &b);
    printf("%d\\n", a + b);
    return 0;
}"""
        code = st.text_area("Or paste C code here", value=sample, height=300)

    st.subheader("2. Submission details")
    submission_id = st.text_input("Submission ID (optional)", value=f"user_{uuid.uuid4().hex[:6]}")

    run_btn = st.button("🚀 Run Autograder")

# --- Right column: results ---
with col2:
    st.subheader("Results")
    result_holder = st.empty()
    download_holder = st.empty()

if run_btn:
    if not code.strip():
        st.error("Please paste code or upload a .c file.")
    else:
        # Prepare inputs and config
        inputs = {}  # initial graph state
        config_payload = {
            "configurable": {
                "submission_id": submission_id or f"user_{int(time.time())}",
                "source_code": code
            }
        }

        progress = st.progress(0)
        status = st.empty()
        status.info("Preparing run...")

        async def run_graph_async():
            # Run the compiled graph with config
            return await g.ainvoke(inputs, config=config_payload)

        try:
            status.info("Running autograder (this may take a few seconds)...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            start_ts = time.time()
            results = loop.run_until_complete(run_graph_async())
            loop.close()
            elapsed = time.time() - start_ts
            progress.progress(100)
        except Exception as e:
            status.error(f"Error while running graph: {e}")
            raise

        # Generate human-readable feedback
        fb = feedback(results)

        # Display summary
        result_holder.markdown(f"### 🏁 Final Score: **{fb['final_score']} / 100**")
        result_holder.write("---")

        # Show where compilation artifacts are (if present)
        compile_info = results.get("compile", {})
        run_dir = compile_info.get("run_dir")
        if run_dir:
            result_holder.caption(f"Run directory: `{run_dir}`")

        # Display sections
        for sec in fb["sections"]:
            section = sec["section"]
            score = sec["score"]
            text = sec["text"]

            if "❌" in text or "Compilation" in section and "❌" in text:
                st.error(f"**{section} — {score}%**\n\n{text}")
            elif "⚠️" in text:
                st.warning(f"**{section} — {score}%**\n\n{text}")
            else:
                st.info(f"**{section} — {score}%**\n\n{text}")

        st.markdown("---")
        st.markdown(f"### 📝 Conclusion\n{fb['conclusion']}")
        st.caption(f"Run time: {elapsed:.2f}s")

        # Downloadable JSON feedback
        json_bytes = json.dumps({"results": results, "feedback": fb}, indent=2).encode("utf-8")
        download_holder.download_button(
            "📥 Download feedback (JSON)",
            data=json_bytes,
            file_name=f"feedback_{submission_id}.json",
            mime="application/json"
        )

        # Clear status and progress
        status.success("Autograder finished.")
        time.sleep(0.2)
        progress.empty()
