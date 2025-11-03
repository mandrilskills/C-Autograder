import time
import os
import subprocess
import json
from typing import List, Annotated, Dict, Any, Optional

from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor, ToolInvocation
from langgraph.channels.base import BaseChannel
from langgraph.channels.last_value import LastValue
from langgraph.graph.graph import make_sync
from langchain_core.pydantic_v1 import BaseModel as PydanticBaseModel

# --- Configuration (Assumed from typical setup) ---
# NOTE: Replace with your actual Gemini model if needed
# The actual LLM setup might be elsewhere, but we include it for completeness
try:
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.0)
except Exception:
    # Placeholder if the user's environment handles LLM initialization externally
    pass


# --- 1. State Definition (Inferred to contain conflicting field names) ---
class GraderState(PydanticBaseModel):
    """Represents the state of the C-Autograder pipeline."""
    code_text: str = Field(description="The submitted C code.")
    tests: str = Field(description="The test cases/input expected output.")

    # These fields must NOT have the same name as the graph nodes
    compile: Optional[dict] = Field(description="Result of compilation step.")
    static: Optional[dict] = Field(description="Result of static analysis step.")
    test: Optional[dict] = Field(description="Result of test execution step.")
    perf: Optional[dict] = Field(description="Result of performance analysis step.")

    # Final combined report and score
    report: str = Field(default="", description="The full grading report text.")
    final_score: float = Field(default=0.0, description="The final calculated score.")

    # Internal tracking
    submission_id: str = Field(description="Unique ID for the submission.")
    messages: List[BaseMessage] = Field(default_factory=list, description="Conversation history for agents.")


# --- 2. Agent Definitions (Placeholders - user's logic is preserved) ---

def compile_agent(state: GraderState) -> GraderState:
    """Agent for compiling the C code."""
    # This function is assumed to contain the actual compilation logic
    print("Agent: Compiling code...")
    # NOTE: The actual compilation logic needs to be here. 
    # For a placeholder, we simulate success.
    # The actual implementation should update the 'compile' key in the state.
    
    # Placeholder for actual C compilation logic using subprocess.run('gcc ...')
    # ...
    
    return {"compile": {"status": "success", "output": "Mock compilation output.", "logs": ""}}

def static_agent(state: GraderState) -> GraderState:
    """Agent for running static analysis (e.g., cppcheck)."""
    print("Agent: Running static analysis...")
    return {"static": {"status": "success", "report": "Mock static analysis report."}}

def test_agent(state: GraderState) -> GraderState:
    """Agent for running functional tests against the compiled binary."""
    print("Agent: Running functional tests...")
    return {"test": {"status": "success", "results": "Mock test results."}}

def performance_agent(state: GraderState) -> GraderState:
    """Agent for running performance/memory checks (e.g., time/valgrind)."""
    print("Agent: Running performance checks...")
    return {"perf": {"status": "success", "metrics": "Mock performance metrics."}}

def orchestrate(state: GraderState) -> GraderState:
    """LLM agent to combine all results and generate the final report and score."""
    print("Agent: Orchestrating feedback and scoring...")
    
    # Placeholder for LLM call logic
    mock_llm_report = (
        "## Grading Report\n"
        "### Compilation: Success\n"
        "### Static Analysis: Minor warnings found.\n"
        "### Functional Tests: 3/5 tests passed.\n"
        "### Performance: Good time complexity, low memory usage.\n"
        "---"
    )
    mock_score = 75.0

    return {
        "report": mock_llm_report,
        "final_score": mock_score,
        "messages": [BaseMessage(content="Orchestration complete.", type="ai")]
    }

# --- 3. Graph Construction (Fix applied here) ---

def build_grader_graph():
    """
    Builds the LangGraph StateGraph for the C-Autograder pipeline.

    FIX: Node names are now suffixed with '_node' to prevent conflicts with 
    the keys in GraderState (e.g., 'compile', 'static'), resolving the ValueError.
    """
    g = StateGraph(GraderState)

    # Renamed nodes to prevent conflict with state keys in GraderState
    g.add_node("compile_node", make_sync(compile_agent))
    g.add_node("static_node", make_sync(static_agent))
    g.add_node("test_node", make_sync(test_agent))
    g.add_node("perf_node", make_sync(performance_agent))
    g.add_node("orchestrate_node", make_sync(orchestrate))

    # Graph flow: compile -> static -> test -> perf -> orchestrate -> END

    # 1. Set Entry Point
    g.set_entry_point("compile_node")

    # 2. Add Edges (sequential flow assumed)
    g.add_edge("compile_node", "static_node")
    g.add_edge("static_node", "test_node")
    g.add_edge("test_node", "perf_node")
    g.add_edge("perf_node", "orchestrate_node")

    # 3. Set Finish Point
    g.add_edge("orchestrate_node", END)

    return g.compile()


def run_grader_pipeline(code_text: str, tests: str) -> Dict[str, Any]:
    """
    Runs the entire grading pipeline using the LangGraph state machine.

    Args:
        code_text: The submitted C code content.
        tests: The test cases/input.

    Returns:
        The structured feedback dictionary from the feedback agent.
    """
    # This is line 263 which was causing the error due to graph build failure
    graph = build_grader_graph()

    submission_id = str(time.time()).replace(".", "") # Unique ID for tracing

    config = {
        "configurable": {
            "submission_id": submission_id,
        }
    }

    # Initial state to pass to the graph
    initial_state = GraderState(
        code_text=code_text,
        tests=tests,
        report="Starting...",
        submission_id=submission_id
    )

    # Run the graph and get the final state
    final_state = graph.invoke(initial_state, config=config)

    # Return the dictionary representation of the final state
    return final_state
