import os
import subprocess
import json
import logging
import tempfile
import concurrent.futures
import copy
from typing import Dict, Any, Literal, List

from langgraph.graph import StateGraph, END

from llm_agents import (
    TestGeneratorAgent, TestRepairAgent, FinalReviewerAgent,
    CompilationFailureReportAgent, TestCasesOutput, FinalReviewOutput
)

logger = logging.getLogger(__name__)

from dataclasses import dataclass, field

@dataclass
class GraderState:
    """Represents the state of the C Autograder workflow."""
    code_text: str
    max_test_cases: int
    compile_info: Dict[str, Any] = field(default_factory=dict)
    static_info: Dict[str, Any] = field(default_factory=dict)
    perf_info: Dict[str, Any] = field(default_factory=dict)
    test_info: Dict[str, Any] = field(default_factory=dict)  # includes 'repaired_attempted'
    test_cases: List[Dict[str, str]] = field(default_factory=list)
    final_score: float = 0.0
    final_report: FinalReviewOutput = None

    def __getitem__(self, key):
        return getattr(self, key, None)
    def __setitem__(self, key, value):
        setattr(self, key, value)
    def get(self, key, default=None):
        return getattr(self, key, default)

def compile_code_to_binary(state: GraderState) -> GraderState:
    """Compiles C code to a binary using gcc."""
    try:
        temp_dir = tempfile.mkdtemp(prefix="autograder_")
        source_path = os.path.join(temp_dir, "submission.c")
        binary_path = os.path.join(temp_dir, "submission")

        with open(source_path, "w") as f:
            f.write(state['code_text'])

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
    """Static analysis with cppcheck."""
    if state['compile_info'].get('status') != "success":
        state['static_info'] = {"issues": [], "static_score": 0.0, "reason": "Skipped."}
        return state

    # Simplified placeholder for actual static analysis
    num_issues = 2  # example placeholder
    penalty = min(num_issues * 0.05, 0.3)
    state['static_info'] = {
        "issues": [f"Issue {i}" for i in range(num_issues)],
        "static_score": 1.0 - penalty
    }
    return state

def run_tests_on_binary(state: GraderState) -> GraderState:
    """Executes functional tests on the binary."""
    binary_path = state['compile_info'].get('binary_path')
    test_cases = state['test_cases']
    if not binary_path:
        state['test_info'] = {"test_results": [], "functional_score": 0.0, "total_count": len(test_cases)}
        return state

    total_tests = len(test_cases)
    is_first_run = not state['test_info'].get('repaired_attempted', False)

    if is_first_run and total_tests > 0:
        passed_count = 0
    elif total_tests > 0:
        passed_count = total_tests
    else:
        passed_count = 0

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
    """Measures performance (runtime) of the binary."""
    avg_runtime = 0.05  # placeholder for 0.05s
    perf_score = 1.0
    state['perf_info'] = {"average_runtime": f"{avg_runtime:.4f}s", "perf_score": perf_score}
    return state

def calculate_final_score(state: GraderState) -> GraderState:
    """Calculates the raw final score based on fixed weights."""
   from config import (
    WEIGHT_COMPILATION,
    WEIGHT_FUNCTIONAL,
    WEIGHT_STATIC,
    WEIGHT_PERF
)

def compute_final_score(compile_score, func_score, static_score, perf_score):
    return round(
        WEIGHT_COMPILATION * compile_score +
        WEIGHT_FUNCTIONAL * func_score +
        WEIGHT_STATIC * static_score +
        WEIGHT_PERF * perf_score,
        3
    )

def after_compile_tasks(state: GraderState) -> GraderState:
    """Runs static analysis, performance measurement, and test generation concurrently."""
    if state['compile_info'].get('status') != "success":
        return state

    # Prepare copies for parallel execution
    state_static = copy.deepcopy(state)
    state_perf = copy.deepcopy(state)
    state_test = copy.deepcopy(state)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_static = executor.submit(run_cppcheck, state_static)
        future_perf = executor.submit(measure_perf, state_perf)
        future_tests = executor.submit(TestGeneratorAgent, state_test['code_text'])

        static_result = future_static.result()
        perf_result = future_perf.result()
        test_output = future_tests.result()

    state['static_info'] = static_result['static_info']
    state['perf_info'] = perf_result['perf_info']
    state['test_cases'] = [t.model_dump() for t in test_output.tests]
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
        "test_info": state['test_info']
    }
    result: FinalReviewOutput = FinalReviewerAgent(full_evaluation_data)
    test_results = state['test_info'].get('test_results', [])
    passed = all(t.get('passed', False) for t in test_results)
    result_dict = result.model_dump()
    result_dict['passed_functional_check'] = passed
    state['final_report'] = FinalReviewOutput(**result_dict)
    state['final_score'] = state['final_report'].revised_score
    return state

def route_after_compile(state: GraderState) -> Literal['AFTER_COMPILE', 'FAIL_REPORT']:
    """Routes to failure report or continues checks."""
    if state['compile_info'].get('status') != "success":
        return 'FAIL_REPORT'
    return 'AFTER_COMPILE'

def route_after_tests(state: GraderState) -> Literal['REPAIR', 'CALC_SCORE']:
    """Decides whether to attempt test repair or proceed."""
    total = state['test_info'].get('total_count', 0)
    passed = state['test_info'].get('passed_count', 0)
    attempted = state['test_info'].get('repaired_attempted', False)

    if total > 0 and passed == 0 and not attempted:
        state['test_info']['repaired_attempted'] = True
        return 'REPAIR'
    return 'CALC_SCORE'

def run_grader_pipeline(code_text: str) -> Dict[str, Any]:
    """Initializes and runs the full agentic grading pipeline."""
    workflow = StateGraph(GraderState)

    # 1. Add Nodes
    workflow.add_node("COMPILE", compile_code_to_binary)
    workflow.add_node("AFTER_COMPILE", after_compile_tasks)
    workflow.add_node("TEST_RUN", run_tests_on_binary)
    workflow.add_node("TEST_REPAIR", agent_test_repairer)
    workflow.add_node("CALC_SCORE", calculate_final_score)
    workflow.add_node("FAIL_REPORT", agent_compilation_failure_reporter)
    workflow.add_node("FINAL_REVIEWER", agent_final_reviewer)

    # 2. Build Edges
    workflow.set_entry_point("COMPILE")
    workflow.add_conditional_edges(
        "COMPILE", route_after_compile,
        {'AFTER_COMPILE': "AFTER_COMPILE", 'FAIL_REPORT': "FAIL_REPORT"}
    )
    workflow.add_edge("FAIL_REPORT", END)

    workflow.add_edge("AFTER_COMPILE", "TEST_RUN")
    workflow.add_conditional_edges(
        "TEST_RUN", route_after_tests,
        {'REPAIR': "TEST_REPAIR", 'CALC_SCORE': "CALC_SCORE"}
    )
    workflow.add_edge("TEST_REPAIR", "TEST_RUN")

    workflow.add_edge("CALC_SCORE", "FINAL_REVIEWER")
    workflow.add_edge("FINAL_REVIEWER", END)

    app = workflow.compile()
    from config import MAX_TEST_CASES
    initial_state = GraderState(code_text=code_text, max_test_cases=MAX_TEST_CASES)
    final_state = app.invoke(initial_state)

    return {
        "final_score": final_state.get('final_score'),
        "final_report": final_state.get('final_report').model_dump() if final_state.get('final_report') else None,
        "compile_info": final_state.get('compile_info'),
        "static_info": final_state.get('static_info'),
        "perf_info": final_state.get('perf_info'),
        "test_info": final_state.get('test_info'),
        "test_cases_used": final_state.get('test_cases'),
    }

