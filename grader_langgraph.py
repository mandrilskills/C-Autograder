# grader_langgraph.py

import os
import subprocess
import json
import logging
import time
from typing import Dict, Any, Literal, List
from langgraph.graph import StateGraph, END
from pydantic import BaseModel # Used only for type hinting GraderState

# Local imports
from llm_agents import (
    TestGeneratorAgent, TestRepairAgent, FinalReviewerAgent, 
    CompilationFailureReportAgent, TestCasesOutput, FinalReviewOutput, TestCase
)

logger = logging.getLogger(__name__)

# --- Graph State Definition (The agent's memory) ---
class GraderState(Dict):
    """Represents the state of the C Autograder workflow."""
    code_text: str
    max_test_cases: int
    
    compile_info: Dict[str, Any] = {}
    static_info: Dict[str, Any] = {}
    perf_info: Dict[str, Any] = {}
    test_info: Dict[str, Any] = {} # Now includes 'repaired_attempted' flag
    
    test_cases: List[Dict[str, str]] = [] 
    final_score: float = 0.0
    final_report: FinalReviewOutput = None


# --- Tool Functions (Execution Nodes - Simplified) ---

def compile_code_to_binary(state: GraderState) -> GraderState:
    # ... (Implementation of compilation logic using subprocess.run)
    # NOTE: Implementation should be detailed in the actual file.
    temp_dir = "/tmp/autograder" 
    os.makedirs(temp_dir, exist_ok=True)
    source_path = os.path.join(temp_dir, "submission.c")
    binary_path = os.path.join(temp_dir, "submission")
    
    with open(source_path, "w") as f: f.write(state['code_text'])
    
    try:
        result = subprocess.run(
            ['gcc', source_path, '-o', binary_path, '-Wall', '-Wextra', '-std=c99'],
            capture_output=True, text=True, timeout=10
        )
        status = "success" if result.returncode == 0 else "error"
        state['compile_info'] = {
            "status": status,
            "stderr": result.stderr,
            "binary_path": binary_path if status == "success" else None
        }
    except subprocess.TimeoutExpired:
        state['compile_info'] = {"status": "error", "stderr": "Compilation timed out."}
    
    return state


def run_cppcheck(state: GraderState) -> GraderState:
    # ... (Implementation of static analysis logic)
    if state['compile_info']['status'] != "success":
        state['static_info'] = {"issues": [], "static_score": 0.0, "reason": "Skipped."}
        return state
        
    # --- Simplified Cppcheck run ---
    # The scoring logic remains: -0.05 per issue, max penalty 0.3
    # ...
    num_issues = 2 # Placeholder for actual Cppcheck result parsing
    penalty = min(num_issues * 0.05, 0.3)
    state['static_info'] = {"issues": [f"Issue {i}" for i in range(num_issues)], "static_score": 1.0 - penalty}
    return state


def run_tests_on_binary(state: GraderState) -> GraderState:
    # ... (Implementation of test execution logic)
    
    binary_path = state['compile_info'].get('binary_path')
    test_cases = state['test_cases']
    
    if not binary_path:
        state['test_info'] = {"test_results": [], "functional_score": 0.0, "total_count": len(test_cases)}
        return state

    # --- Simplified Test Execution ---
    # NOTE: Assuming one test case in the first run will fail, leading to repair.
    # In a real run, it executes the code with inputs.
    
    results = []
    passed_count = 0
    total_tests = len(test_cases)

    # Simplified logic to demonstrate repair: If this is the first run, assume 0 passed
    # If it's the second run (after repair), assume a better result
    is_first_run = not state['test_info'].get('repaired_attempted', False)
    
    if is_first_run and total_tests > 0:
        passed_count = 0 # Force 0 passed to trigger the Test Repair Agent
    elif total_tests > 0:
        passed_count = total_tests # Assume repair fixed the issue
    
    functional_score = passed_count / total_tests if total_tests > 0 else 0.0
    
    state['test_info'] = {
        "test_results": [{"passed": True}] * passed_count + [{"passed": False}] * (total_tests - passed_count),
        "functional_score": functional_score,
        "passed_count": passed_count,
        "total_count": total_tests,
        "repaired_attempted": state['test_info'].get('repaired_attempted', False)
    }
    return state


def measure_perf(state: GraderState) -> GraderState:
    # ... (Implementation of performance measurement logic)
    
    # Assume success for the purpose of the structure
    avg_runtime = 0.05 # Placeholder: 0.05s
    perf_score = 1.0
    state['perf_info'] = {"average_runtime": f"{avg_runtime:.4f}s", "perf_score": perf_score}
    return state


def calculate_final_score(state: GraderState) -> GraderState:
    """Calculates the raw final score based on fixed weights."""
    W_FUNC, W_STATIC, W_PERF = 0.50, 0.30, 0.20
    
    if state['compile_info']['status'] != "success":
        final_score = 0.0
    else:
        func_score = state['test_info'].get('functional_score', 0.0)
        static_score = state['static_info'].get('static_score', 0.0)
        perf_score = state['perf_info'].get('perf_score', 0.0)
        final_score = (func_score * W_FUNC) + (static_score * W_STATIC) + (perf_score * W_PERF)
        
    state['final_score'] = final_score
    return state


# --- LLM Agent Node Wrappers ---

def agent_test_generator(state: GraderState) -> GraderState:
    result: TestCasesOutput = TestGeneratorAgent(state['code_text'])
    state['test_cases'] = [t.model_dump() for t in result.tests]
    return state

def agent_test_repairer(state: GraderState) -> GraderState:
    result: TestCasesOutput = TestRepairAgent(state['code_text'], state['test_info'])
    if result.status == "repaired" and result.tests:
        state['test_cases'] = [t.model_dump() for t in result.tests]
    return state

def agent_compilation_failure_reporter(state: GraderState) -> GraderState:
    result: FinalReviewOutput = CompilationFailureReportAgent(state['compile_info'])
    state['final_report'] = result
    state['final_score'] = result.revised_score
    return state

def agent_final_reviewer(state: GraderState) -> GraderState:
    full_evaluation_data = {
        "final_score": state['final_score'],
        "compile_info": state['compile_info'],
        "static_info": state['static_info'],
        "perf_info": state['perf_info'],
        "test_info": state['test_info'],
    }
    result: FinalReviewOutput = FinalReviewerAgent(full_evaluation_data)
    state['final_report'] = result
    state['final_score'] = result.revised_score # Final score updated by LLM Reviewer
    return state


# --- Conditional Routing Functions (The Agent's Decision Logic) ---

def route_after_compile(state: GraderState) -> Literal['FAIL_REPORT', 'STATIC_CHECK']:
    """Decider Agent: Routes to failure report or continues checks."""
    if state['compile_info']['status'] != "success":
        return 'FAIL_REPORT'
    return 'STATIC_CHECK'

def route_after_tests(state: GraderState) -> Literal['REPAIR', 'PERFORMANCE']:
    """Test Failure Router: Decides whether to attempt test repair."""
    total = state['test_info'].get('total_count', 0)
    passed = state['test_info'].get('passed_count', 0)
    attempted = state['test_info'].get('repaired_attempted', False)
    
    # Attempt repair only if 0/N tests passed AND no repair has been attempted yet
    if total > 0 and passed == 0 and not attempted:
        state['test_info']['repaired_attempted'] = True
        return 'REPAIR'
        
    # Otherwise, proceed to performance check (or final report if subsequent step is missing)
    return 'PERFORMANCE'

# --- Build the LangGraph ---

def run_grader_pipeline(code_text: str) -> Dict[str, Any]:
    """Initializes and runs the full agentic grading pipeline."""
    
    workflow = StateGraph(GraderState)
    
    # 1. Add Nodes
    workflow.add_node("TEST_GEN", agent_test_generator)
    workflow.add_node("COMPILE", compile_code_to_binary)
    workflow.add_node("STATIC_CHECK", run_cppcheck)
    workflow.add_node("PERFORMANCE", measure_perf)
    workflow.add_node("TEST_RUN", run_tests_on_binary)
    workflow.add_node("TEST_REPAIR", agent_test_repairer)
    workflow.add_node("CALC_SCORE", calculate_final_score)
    workflow.add_node("FAIL_REPORT", agent_compilation_failure_reporter)
    workflow.add_node("FINAL_REVIEWER", agent_final_reviewer)

    # 2. Build Edges

    # Start: Generate tests -> Compile
    workflow.set_entry_point("TEST_GEN")
    workflow.add_edge("TEST_GEN", "COMPILE")
    
    # Compile -> Decider Agent
    workflow.add_conditional_edges(
        "COMPILE",
        route_after_compile,
        {'STATIC_CHECK': "STATIC_CHECK", 'FAIL_REPORT': "FAIL_REPORT"}
    )
    workflow.add_edge("FAIL_REPORT", END) # End of flow for compilation failure

    # Static Check -> Test Run (Sequential)
    workflow.add_edge("STATIC_CHECK", "TEST_RUN")

    # Test Run -> Test Failure Router
    workflow.add_conditional_edges(
        "TEST_RUN",
        route_after_tests,
        {'REPAIR': "TEST_REPAIR", 'PERFORMANCE': "PERFORMANCE"}
    )
    
    # Test Repair -> Loop back to re-run tests on the new cases
    workflow.add_edge("TEST_REPAIR", "TEST_RUN") 

    # Normal Path
    workflow.add_edge("PERFORMANCE", "CALC_SCORE")
    workflow.add_edge("CALC_SCORE", "FINAL_REVIEWER")

    # End
    workflow.add_edge("FINAL_REVIEWER", END)
    
    app = workflow.compile()

    initial_state = GraderState(code_text=code_text, max_test_cases=5)
    
    final_state = app.invoke(initial_state)

    # Return the final state data for the app to display
    return {
        "final_score": final_state.get('final_score'),
        "final_report": final_state.get('final_report').model_dump() if final_state.get('final_report') else None,
        "compile_info": final_state.get('compile_info'),
        "static_info": final_state.get('static_info'),
        "perf_info": final_state.get('perf_info'),
        "test_info": final_state.get('test_info'),
        "test_cases_used": final_state.get('test_cases'),
    }
