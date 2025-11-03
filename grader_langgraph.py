"""
grader_langgraph.py

A small grader pipeline that:
- defines a GraderState Pydantic model
- provides agents (compile, static analysis, run tests, performance)
- orchestrates calls and returns a final dict.

IMPORTANT SECURITY NOTE:
- The compile_and_run functions in this file run the submitted C code using subprocess.
  This is UNSAFE on an unprotected host. For production, run student code inside a sandbox
  (Docker container, firejail, gVisor, etc.). The example below uses a simple, limited
  subprocess approach for convenience/testing only.
"""

from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel
import tempfile
import subprocess
import os
import shutil
import time
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class GraderState(BaseModel):
    # Inputs
    code: str
    tests: List[str] = []

    # Intermediate / outputs
    compile: Optional[Dict[str, Any]] = None
    static: Optional[Dict[str, Any]] = None
    test: Optional[Dict[str, Any]] = None
    perf: Optional[Dict[str, Any]] = None

    # Final
    report: Optional[str] = None
    final_score: Optional[float] = None
    messages: Optional[List[Dict[str, Any]]] = None


###############################################################################
# Utility: compile code in a temporary directory
###############################################################################
def compile_c_code(code_text: str, timeout_seconds: int = 10) -> Dict[str, Any]:
    """
    Compile C code with gcc in a temporary directory.

    Returns dict:
      {
        "status": "success"|"error",
        "binary_path": "/tmp/...",
        "stdout": "...",
        "stderr": "...",
        "returncode": 0
      }

    WARNING: Running untrusted code on the host is unsafe. Use sandboxing in production.
    """
    result = {"status": "error", "binary_path": None, "stdout": "", "stderr": "", "returncode": None}
    tmpdir = tempfile.mkdtemp(prefix="grader_compile_")
    src_path = os.path.join(tmpdir, "submission.c")
    bin_path = os.path.join(tmpdir, "submission_bin")
    try:
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code_text)

        # run gcc
        proc = subprocess.run(["gcc", src_path, "-o", bin_path], capture_output=True, text=True, timeout=timeout_seconds)
        result["stdout"] = proc.stdout or ""
        result["stderr"] = proc.stderr or ""
        result["returncode"] = proc.returncode
        if proc.returncode == 0 and os.path.exists(bin_path):
            result["status"] = "success"
            result["binary_path"] = bin_path
        else:
            result["status"] = "error"
    except subprocess.TimeoutExpired as te:
        result["stderr"] = f"Compilation timed out after {timeout_seconds}s."
        result["returncode"] = -1
        result["status"] = "error"
    except Exception as e:
        result["stderr"] = str(e)
        result["status"] = "error"
    # We intentionally don't delete tmpdir: caller should remove binary when done (for safety)
    return result


def run_binary_with_input(bin_path: str, input_data: str, timeout_seconds: int = 3) -> Dict[str, Any]:
    """
    Run the compiled binary with given input_data (string), returning stdout/stderr/rc/time.
    """
    result = {"stdout": "", "stderr": "", "returncode": None, "time": None}
    if not os.path.exists(bin_path) or not os.access(bin_path, os.X_OK):
        result["stderr"] = "Binary not found or not executable."
        return result

    start = time.time()
    try:
        proc = subprocess.run([bin_path], input=input_data, capture_output=True, text=True, timeout=timeout_seconds)
        elapsed = time.time() - start
        result["stdout"] = proc.stdout or ""
        result["stderr"] = proc.stderr or ""
        result["returncode"] = proc.returncode
        result["time"] = elapsed
    except subprocess.TimeoutExpired:
        result["stderr"] = f"Execution timed out after {timeout_seconds}s."
        result["returncode"] = -1
        result["time"] = timeout_seconds
    except Exception as e:
        result["stderr"] = str(e)
        result["returncode"] = -1
        result["time"] = None
    return result


###############################################################################
# Agents
###############################################################################
def compile_agent(state: GraderState) -> Dict[str, Any]:
    """
    Compile the submitted code and update state.
    Returns a dict with the key 'compile' to be merged into the state.
    """
    logger.info("compile_agent: compiling code...")
    compile_res = compile_c_code(state.code, timeout_seconds=12)
    # If compile succeeded, leave binary path in compile output (caller should cleanup)
    return {"compile": compile_res}


def static_agent(state: GraderState) -> Dict[str, Any]:
    """
    Very simple static analysis: check for use of forbidden functions (e.g., system),
    presence of main, and approximate length. For production, plug in clang-tidy or cppcheck.
    """
    logger.info("static_agent: running simple static checks...")
    code = state.code or ""
    issues = []
    if "system(" in code:
        issues.append("Use of system(...) detected — disallowed in grading environment.")
    if "gets(" in code:
        issues.append("Use of gets(...) detected — unsafe function.")
    if "main(" not in code:
        issues.append("No main() found; program may not be runnable.")
    length = len(code.splitlines())
    summary = {"issues": issues, "lines": length}
    return {"static": summary}


def test_agent(state: GraderState) -> Dict[str, Any]:
    """
    Run functional tests provided in state.tests.
    Each test string is expected to be of the form 'input::expected_output' (best-effort).
    Returns a dict with test results and counts.
    """
    logger.info("test_agent: running functional tests...")
    compile_info = state.compile or {}
    if compile_info.get("status") != "success" or not compile_info.get("binary_path"):
        return {"test": {"status": "skipped", "reason": "Compilation failed or binary missing", "results": []}}

    bin_path = compile_info["binary_path"]
    results = []
    passed = 0
    total = len(state.tests or [])
    for t in state.tests or []:
        input_part, expected = "", ""
        if "::" in t:
            input_part, expected = t.split("::", 1)
        elif "->" in t:
            input_part, expected = t.split("->", 1)
        else:
            input_part, expected = t, ""

        input_str = input_part.strip()
        expected_str = expected.strip()

        exec_res = run_binary_with_input(bin_path, input_str, timeout_seconds=2)
        out = (exec_res.get("stdout") or "").strip()
        passed_now = False
        # Conservative comparison: strip and compare
        if expected_str == "":
            # If no expected provided, mark as 'ran' but not pass/fail
            outcome = {"input": input_str, "expected": expected_str, "output": out, "pass": None, "meta": exec_res}
        else:
            pass_flag = (out == expected_str)
            if pass_flag:
                passed += 1
            outcome = {"input": input_str, "expected": expected_str, "output": out, "pass": pass_flag, "meta": exec_res}
        results.append(outcome)

    score = None
    if total > 0:
        score = round((passed / total) * 100.0, 2)
    return {"test": {"status": "done", "results": results, "passed": passed, "total": total, "score": score}}


def performance_agent(state: GraderState) -> Dict[str, Any]:
    """
    Simple perf checks: average runtime across tests and mark if any test timed out.
    """
    logger.info("performance_agent: measuring performance...")
    test_info = state.test or {}
    results = test_info.get("results", [])
    times = []
    timed_out = False
    for r in results:
        meta = r.get("meta", {}) or {}
        t = meta.get("time")
        if t is not None:
            times.append(t)
        if meta.get("returncode") == -1 and "timed out" in (meta.get("stderr") or ""):
            timed_out = True

    avg = sum(times) / len(times) if times else None
    perf_summary = {"average_time": avg, "any_timeouts": timed_out}
    return {"perf": perf_summary}


def orchestrate(state: GraderState, llm_reporter=None) -> Dict[str, Any]:
    """
    Final orchestration: compute a final score (weighted), ask LLM for a text report
    (if llm_reporter provided), and return report + final_score.
    llm_reporter is expected to be a callable that accepts a context dict and returns a string.
    """
    logger.info("orchestrate: computing final score and report...")
    # Combine scores: compile pass gives base points, tests give majority, perf small bonus
    compile_ok = 1 if (state.compile or {}).get("status") == "success" else 0
    test_info = state.test or {}
    test_score = test_info.get("score")
    perf_info = state.perf or {}
    perf_bonus = 5.0 if not perf_info.get("any_timeouts", False) else 0.0

    computed_score = 0.0
    if test_score is not None:
        # Weighted: tests 85%, compile 10%, perf 5%
        computed_score = round((0.85 * test_score) + (0.10 * (100.0 if compile_ok else 0.0)) + (0.05 * perf_bonus), 2)
    else:
        # fallback: 50 if compiled else 0
        computed_score = 50.0 if compile_ok else 0.0

    context = {
        "code": state.code,
        "compile": state.compile,
        "static": state.static,
        "test": state.test,
        "perf": state.perf,
        "score": computed_score,
    }

    report_text = None
    if llm_reporter:
        try:
            report_text = llm_reporter(context)
        except Exception as e:
            logger.exception("LLM reporter failed: %s", e)
            report_text = None

    # Basic textual fallback report if LLM not available
    if not report_text:
        lines = [
            "## Automated Grading Report (fallback)",
            f"Final score: {computed_score}",
            "",
            "### Compilation",
            str(state.compile),
            "",
            "### Static Analysis",
            str(state.static),
            "",
            "### Tests",
            str(state.test),
            "",
            "### Performance",
            str(state.perf),
        ]
        report_text = "\n".join(lines)

    return {"report": report_text, "final_score": float(computed_score), "messages": [{"type": "system", "content": "orchestration complete"}]}


###############################################################################
# Pipeline runner
###############################################################################
def run_grader_pipeline(code_text: str, tests: Optional[List[str]] = None, llm_reporter=None) -> Dict[str, Any]:
    """
    Runs the pipeline in sequence:
      - compile
      - static
      - test
      - perf
      - orchestrate (final)

    Returns a plain dict suitable for serialization (JSON).
    """
    state = GraderState(code=code_text, tests=tests or [])
    try:
        # compile
        compile_out = compile_agent(state)
        state.compile = compile_out.get("compile")
        # static
        static_out = static_agent(state)
        state.static = static_out.get("static")
        # tests
        test_out = test_agent(state)
        state.test = test_out.get("test")
        # perf
        perf_out = performance_agent(state)
        state.perf = perf_out.get("perf")
        # orchestrate
        orch_out = orchestrate(state, llm_reporter=llm_reporter)
        state.report = orch_out.get("report")
        state.final_score = orch_out.get("final_score")
        state.messages = orch_out.get("messages")
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        # return partial state with error info
        return {"error": str(e), **state.dict()}

    # Convert to dict for UI consumption
    return state.dict()
