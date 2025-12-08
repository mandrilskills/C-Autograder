# llm_agents.py
"""
Simplified local 'agents' used by the pipeline.
These are intentionally lightweight and deterministic fallbacks so the app can run offline.
"""

import re
from typing import List, Dict, Any

def generate_tests_from_code(code_text: str, max_cases: int = 3) -> List[Dict[str, str]]:
    """
    Heuristic test generator: tries to detect simple input patterns and create
    a few minimal tests. This is a fallback generator (no LLM).
    """
    tests = []
    # If code contains scanf or reading integers, produce integer tests
    if re.search(r'\bscanf\s*\(|\bscanf_s\s*\(', code_text):
        tests = [
            {"input": "1\n", "expected": "1"},
            {"input": "2\n", "expected": "2"},
            {"input": "10\n", "expected": "10"},
        ]
    else:
        # fallback: no-input run
        tests = [{"input": "", "expected": ""}]
    return tests[:max_cases]


def compilation_failure_report(compile_info: Dict[str, Any], code_text: str) -> Dict[str, Any]:
    """
    Produce a helpful structured report when compilation fails.
    """
    stderr = compile_info.get("stderr", "")
    short_err = stderr.splitlines()[:8]
    # Basic heuristics for partial grading
    has_main = bool(re.search(r'\bint\s+main\s*\(|\bint\s+main\s*\(', code_text))
    includes = re.findall(r'#include\s*<([^>]+)>', code_text)
    style_issues = []
    if not has_main:
        style_issues.append("Missing main() function.")
    if "stdio.h" not in includes:
        style_issues.append("stdio.h not included (maybe no IO present).")
    return {
        "summary": "Compilation failed. See stderr for details.",
        "stderr_preview": "\n".join(short_err),
        "heuristics": {
            "has_main": has_main,
            "includes": includes,
            "style_issues": style_issues
        }
    }


def final_reviewer(full_eval: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lightweight final reviewer that formats the evaluation and returns a human-readable
    structured report (no external LLM).
    """
    final_score = full_eval.get("final_score", 0.0)
    compile_info = full_eval.get("compile_info", {})
    test_info = full_eval.get("test_info", {})
    static_info = full_eval.get("static_info", {})
    perf_info = full_eval.get("perf_info", {})

    comments = []
    if compile_info.get("status") != "success":
        comments.append("Compilation failed; awarded partial marks based on code structure and heuristics.")
    else:
        comments.append("Compiled successfully. Functional tests and static analysis evaluated.")

    # Add concise pointer comments
    if static_info.get("errors", 0) > 0:
        comments.append(f"Static analysis reported {static_info.get('errors')} issue(s).")
    if test_info.get("passed_count", 0) < test_info.get("total_count", 0):
        comments.append(f"Passed {test_info.get('passed_count')} / {test_info.get('total_count')} test(s).")

    return {
        "final_score": final_score,
        "comments": comments,
        "detailed": {
            "compile_info": compile_info,
            "test_info": test_info,
            "static_info": static_info,
            "perf_info": perf_info
        }
    }
