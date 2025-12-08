# grader_langgraph.py
"""
Minimal grading pipeline for local development.
- Writes code to temp dir
- Attempts to compile with gcc
- Runs cppcheck (if installed) for static analysis
- Generates tests using a heuristic generator (llm_agents.generate_tests_from_code)
- Runs tests against compiled binary (if compiled)
- Measures execution time
- Computes weighted score (functional/static/perf)
- Awards partial credit on compile failure using heuristics
"""

import os
import tempfile
import subprocess
import time
import shutil
import json
import re
from typing import Dict, Any, List

from config import (
    MAX_TEST_CASES, TEMP_DIR_PREFIX, COMPILE_TIMEOUT, RUN_TIMEOUT, CPPcheck_TIMEOUT,
    WEIGHT_FUNCTIONAL, WEIGHT_STATIC, WEIGHT_PERF, PARTIAL_ON_COMPILE_FAIL
)
from llm_agents import generate_tests_from_code, compilation_failure_report, final_reviewer

# Helper functions
def safe_run(cmd: List[str], cwd: str = None, timeout: int = 10) -> Dict[str, Any]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        return {"returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "TimeoutExpired"}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}

def compile_code(src_path: str, workdir: str) -> Dict[str, Any]:
    out_bin = os.path.join(workdir, "main")
    cmd = ["gcc", "-std=c11", "-O2", "-Wall", "-Werror", src_path, "-o", out_bin]
    result = safe_run(cmd, cwd=workdir, timeout=COMPILE_TIMEOUT)
    status = "success" if result["returncode"] == 0 else "failure"
    return {"status": status, "returncode": result["returncode"], "stdout": result["stdout"], "stderr": result["stderr"], "binary": out_bin if status == "success" else None}

def run_binary(binary_path: str, stdin_data: str, timeout: int = RUN_TIMEOUT) -> Dict[str, Any]:
    try:
        p = subprocess.run([binary_path], input=stdin_data.encode(), capture_output=True, timeout=timeout)
        stdout = p.stdout.decode(errors="replace").strip()
        return {"timeout": False, "returncode": p.returncode, "stdout": stdout, "stderr": p.stderr.decode(errors="replace")}
    except subprocess.TimeoutExpired:
        return {"timeout": True, "returncode": None, "stdout": "", "stderr": "TimeoutExpired"}
    except Exception as e:
        return {"timeout": False, "returncode": -1, "stdout": "", "stderr": str(e)}

def run_cppcheck(src_path: str, workdir: str) -> Dict[str, Any]:
    cmd = ["cppcheck", "--enable=all", "--inline-suppr", "--template=gcc", src_path]
    res = safe_run(cmd, cwd=workdir, timeout=CPPcheck_TIMEOUT)
    # Parse simple line count of stderr (cppcheck writes to stderr)
    stderr = res.get("stderr", "")
    issues = stderr.strip().splitlines() if stderr.strip() else []
    return {"returncode": res["returncode"], "raw": stderr, "issues": issues, "errors": len(issues)}

def code_quality_heuristic(code_text: str) -> float:
    """
    Returns a heuristic score between 0 and 1 estimating code quality/structure.
    Used for partial credit when compilation fails.
    """
    score = 0.0
    # presence of main
    if re.search(r'\bint\s+main\s*\(|\bint\s+main\s*\(', code_text):
        score += 0.4
    # includes
    if re.search(r'#include\s*<stdio.h>', code_text):
        score += 0.2
    # function decomposition: count 'int ' or 'void ' function definitions
    funcs = re.findall(r'\n\s*(?:int|void|char|double|float)\s+[A-Za-z_][A-Za-z0-9_]*\s*\(', code_text)
    if len(funcs) >= 1:
        score += 0.2
    # semicolon ratio heuristic (not perfect)
    semicolons = code_text.count(';')
    if semicolons >= 2:
        score += 0.2
    return min(1.0, score)

def compare_output(expected: str, actual: str) -> bool:
    # Simple strip/normalize whitespace compare
    return expected.strip() == actual.strip()

def compute_scores(functional_score: float, static_score: float, perf_score: float) -> Dict[str, float]:
    # clamp
    functional_score = max(0.0, min(1.0, functional_score))
    static_score = max(0.0, min(1.0, static_score))
    perf_score = max(0.0, min(1.0, perf_score))
    final_score = WEIGHT_FUNCTIONAL * functional_score + WEIGHT_STATIC * static_score + WEIGHT_PERF * perf_score
    return {"functional": functional_score, "static": static_score, "perf": perf_score, "final_score": final_score}

def run_grader_pipeline(code_text: str) -> Dict[str, Any]:
    """
    Main entrypoint used by the Streamlit app.
    Returns a dict with keys:
    - final_score (float)
    - final_report (dict)
    - compile_info, static_info, test_info, perf_info, test_cases_used
    """
    tmpdir = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)
    try:
        src_path = os.path.join(tmpdir, "main.c")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code_text)

        compile_info = compile_code(src_path, tmpdir)

        # Static analysis (cppcheck) — best-effort
        static_info = run_cppcheck(src_path, tmpdir)

        # Generate tests (heuristic)
        test_cases = generate_tests_from_code(code_text, max_cases=MAX_TEST_CASES)

        test_info = {"test_results": [], "passed_count": 0, "total_count": len(test_cases)}
        perf_info = {"timings": []}

        if compile_info.get("status") == "success" and compile_info.get("binary"):
            binary = compile_info["binary"]
            passed = 0
            timings = []
            for t in test_cases:
                inp = t.get("input", "")
                expected = t.get("expected", "")
                start = time.perf_counter()
                res = run_binary(binary, inp, timeout=RUN_TIMEOUT)
                elapsed = time.perf_counter() - start
                timings.append(elapsed)
                ok = (not res.get("timeout")) and compare_output(expected, res.get("stdout", ""))
                test_info["test_results"].append({
                    "input": inp,
                    "expected": expected,
                    "actual": res.get("stdout", ""),
                    "passed": ok,
                    "stderr": res.get("stderr", ""),
                    "timeout": res.get("timeout", False),
                    "elapsed_s": elapsed
                })
                if ok:
                    passed += 1
            test_info["passed_count"] = passed
            test_info["total_count"] = len(test_cases)
            # Compute functional score from tests (fraction passed)
            functional_score = (passed / max(1, len(test_cases))) if len(test_cases) > 0 else 0.0
            # Performance score: simple heuristic — if average time < RUN_TIMEOUT/2 -> full marks
            avg_time = sum(timings) / max(1, len(timings))
            perf_score = 1.0 if avg_time <= (RUN_TIMEOUT / 2) else max(0.0, 1.0 - (avg_time - (RUN_TIMEOUT / 2)) / RUN_TIMEOUT)
            perf_info["timings"] = timings
            perf_info["average_s"] = avg_time
            # Static score: map number of cppcheck issues to 0..1 (0 issues -> 1.0)
            static_score = 1.0 if static_info.get("errors", 0) == 0 else max(0.0, 1.0 - static_info.get("errors", 0) * 0.15)
        else:
            # Compilation failed: award partial credit if allowed
            heur = code_quality_heuristic(code_text)
            functional_score = heur if PARTIAL_ON_COMPILE_FAIL else 0.0
            # static_score: use cppcheck info but reduce because binary not produced
            static_score = 1.0 if static_info.get("errors", 0) == 0 else max(0.0, 1.0 - static_info.get("errors", 0) * 0.15)
            perf_score = 0.0  # can't measure perf without binary
            # Populate test_info with "could not run" entries
            for t in test_cases:
                test_info["test_results"].append({
                    "input": t.get("input", ""),
                    "expected": t.get("expected", ""),
                    "actual": None,
                    "passed": False,
                    "stderr": "Not run: compilation failed",
                    "timeout": False,
                    "elapsed_s": None
                })
            test_info["passed_count"] = 0
            test_info["total_count"] = len(test_cases)

        scores = compute_scores(functional_score, static_score, perf_score)

        full_eval = {
            "final_score": scores["final_score"],
            "scores_breakdown": scores,
            "compile_info": compile_info,
            "static_info": static_info,
            "test_info": test_info,
            "perf_info": perf_info,
            "test_cases_used": test_cases
        }

        # Final reviewer (local)
        final_report = final_reviewer(full_eval)
        full_eval["final_report"] = final_report

        return full_eval

    finally:
        # Keep tmpdir for debugging if needed? For now remove it.
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass
