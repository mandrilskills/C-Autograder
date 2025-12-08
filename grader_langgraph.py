# grader_langgraph.py
import os
import subprocess
import time
import json
import shutil
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

from config import *
from llm_agents import (
    generate_tests_agent,
    repair_tests_agent,
    compile_failure_agent,
    final_reviewer_agent
)

os.makedirs(TEMP_DIR, exist_ok=True)

@dataclass
class GraderState:
    code_text: str
    compile_info: dict = None
    test_results: dict = None
    static_results: dict = None
    perf_results: dict = None
    final_score: float = 0.0
    final_report: dict = None


# -------------------- COMPILATION --------------------
def compile_code(state: GraderState):
    c_path = os.path.join(TEMP_DIR, "main.c")
    exe_path = os.path.join(TEMP_DIR, "main.out")

    with open(c_path, "w") as f:
        f.write(state.code_text)

    try:
        proc = subprocess.run(
            ["gcc", c_path, "-o", exe_path],
            capture_output=True,
            text=True,
            timeout=10
        )

        success = proc.returncode == 0
        compile_score = WEIGHT_COMPILATION if success else WEIGHT_COMPILATION * 0.4

        state.compile_info = {
            "status": "success" if success else "failed",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "score": compile_score
        }

    except Exception as e:
        state.compile_info = {
            "status": "error",
            "stderr": str(e),
            "score": WEIGHT_COMPILATION * 0.2
        }

    return state


# -------------------- STATIC ANALYSIS --------------------
def run_static_analysis(state: GraderState):
    c_path = os.path.join(TEMP_DIR, "main.c")

    try:
        proc = subprocess.run(
            ["cppcheck", "--enable=all", "--quiet", c_path],
            capture_output=True,
            text=True,
            timeout=10
        )

        issues = proc.stderr.strip().splitlines()
        issue_count = len(issues)

        if issue_count == 0:
            static_score = WEIGHT_STATIC
        elif issue_count <= 3:
            static_score = WEIGHT_STATIC * 0.7
        else:
            static_score = WEIGHT_STATIC * 0.4

        state.static_results = {
            "issues_found": issue_count,
            "details": issues,
            "score": static_score
        }

    except Exception as e:
        state.static_results = {
            "issues_found": 0,
            "details": [str(e)],
            "score": WEIGHT_STATIC * 0.3
        }

    return state


# -------------------- TEST EXECUTION --------------------
def execute_tests(state: GraderState):
    exe_path = os.path.join(TEMP_DIR, "main.out")
    tests = generate_tests_agent(state.code_text)

    passed = 0
    outputs = []

    for test in tests:
        try:
            proc = subprocess.run(
                [exe_path],
                input=test["input"],
                text=True,
                capture_output=True,
                timeout=5
            )

            actual = proc.stdout.strip()
            expected = test["output"].strip()

            if actual == expected:
                passed += 1

            outputs.append({
                "input": test["input"],
                "expected": expected,
                "actual": actual
            })

        except Exception as e:
            outputs.append({"error": str(e)})

    total = len(tests)
    func_score = (passed / total) * WEIGHT_FUNCTIONAL if total else 0

    state.test_results = {
        "passed": passed,
        "total": total,
        "details": outputs,
        "score": func_score
    }

    return state


# -------------------- PERFORMANCE TESTING --------------------
def run_performance(state: GraderState):
    exe_path = os.path.join(TEMP_DIR, "main.out")

    try:
        start = time.time()
        subprocess.run([exe_path], input="10\n", text=True, timeout=3)
        end = time.time()

        runtime = end - start

        if runtime <= 0.2:
            perf_score = WEIGHT_PERF
        elif runtime <= 0.5:
            perf_score = WEIGHT_PERF * 0.7
        else:
            perf_score = WEIGHT_PERF * 0.4

        state.perf_results = {
            "runtime": runtime,
            "score": perf_score
        }

    except:
        state.perf_results = {
            "runtime": None,
            "score": WEIGHT_PERF * 0.3
        }

    return state


# -------------------- FINAL PIPELINE --------------------
def run_grader_pipeline(code_text: str):
    state = GraderState(code_text=code_text)

    state = compile_code(state)

    if state.compile_info["status"] == "failed":
        state.final_report = compile_failure_agent(state)
        total = state.compile_info["score"]
        state.final_score = round(total, 2)
        return state.__dict__

    with ThreadPoolExecutor() as executor:
        state = executor.submit(run_static_analysis, state).result()
        state = executor.submit(execute_tests, state).result()
        state = executor.submit(run_performance, state).result()

    total_score = (
        state.compile_info["score"] +
        state.static_results["score"] +
        state.test_results["score"] +
        state.perf_results["score"]
    )

    total_score = min(max(round(total_score, 3), 0), 1)

    state.final_score = total_score
    state.final_report = final_reviewer_agent(state)

    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    return state.__dict__
