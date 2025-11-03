# grader_langgraph.py
"""
Core grader that compiles via gcc, statically analyses with cppcheck,
executes test cases, measures simple performance, orchestrates results into JSON,
and requests LLM to write final human-readable report (LLM ONLY for report generation).
Also builds a PDF report for download.
"""

import os
import subprocess
import tempfile
import time
import shutil
import json
import logging
from io import BytesIO
from typing import List, Dict, Any, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------- Compilation ----------
def compile_code(code_text: str) -> Dict[str, Any]:
    temp_dir = tempfile.mkdtemp(prefix="grader_compile_")
    source_path = os.path.join(temp_dir, "submission.c")
    binary_path = os.path.join(temp_dir, "submission_bin")

    with open(source_path, "w") as f:
        f.write(code_text)

    # compile with warnings enabled; include strict flags
    compile_cmd = ["gcc", source_path, "-o", binary_path, "-std=c11", "-Wall", "-Wextra"]
    proc = subprocess.run(compile_cmd, capture_output=True, text=True, cwd=temp_dir)
    compile_info = {
        "status": "success" if proc.returncode == 0 else "error",
        "binary_path": binary_path if proc.returncode == 0 else None,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
        "temp_dir": temp_dir,
    }
    return compile_info

# ---------- Static analysis ----------
def analyze_code_static(source_path: str) -> Dict[str, Any]:
    # source_path must point to the C file
    issues = []
    # Run cppcheck if installed
    try:
        cpp = subprocess.run(
            ["cppcheck", "--enable=warning,style,performance,portability", source_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10, cwd=os.path.dirname(source_path)
        )
        out = cpp.stdout + cpp.stderr
        # collect non-empty lines as issues (cppcheck emits on stderr)
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            # Ignore summary lines from cppcheck
            if line.startswith("Checking") or line.startswith("Note:"):
                continue
            issues.append(line)
    except FileNotFoundError:
        # cppcheck not installed — fall back to heuristic scanning
        issues.append("cppcheck not available - fell back to heuristic checks")
    except Exception as e:
        logger.warning("cppcheck run failed: %s", e)
        issues.append(f"cppcheck error: {e}")

    # Additional heuristic checks (LLM must not be used here)
    try:
        with open(source_path, "r") as f:
            code = f.read()
        if "gets(" in code:
            issues.append("Use of unsafe function gets()")
        if "system(" in code:
            issues.append("Use of system() call")
        if "while(1)" in code or "for(;;)" in code:
            issues.append("Potential infinite loop pattern detected")
    except Exception:
        pass

    return {"issues": issues, "count": len(issues)}

# ---------- Test runner ----------
def run_test_cases(compile_info: Dict[str, Any], tests: List[str], timeout_per_test: int = 3) -> Dict[str, Any]:
    if not compile_info.get("binary_path"):
        return {"status": "error", "passed": 0, "total": len(tests), "results": [], "score": 0}

    binary_path = compile_info["binary_path"]
    results = []
    passed = 0
    total = len(tests)

    for case in tests:
        if "::" not in case:
            # ignore malformed lines but include as fail
            results.append({
                "raw": case,
                "input": None,
                "expected": None,
                "actual": None,
                "time": None,
                "success": False,
                "error": "malformed test (expected format input::expected_output)"
            })
            continue
        input_data, expected_output = case.split("::", 1)
        input_bytes = input_data.encode()
        try:
            start = time.time()
            proc = subprocess.run(
                [binary_path],
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_per_test,
                cwd=os.path.dirname(binary_path)
            )
            elapsed = round(time.time() - start, 6)
            actual_output = proc.stdout.decode(errors="ignore").strip()
            success = actual_output == expected_output.strip()
            record = {
                "input": input_data,
                "expected": expected_output.strip(),
                "actual": actual_output,
                "stderr": proc.stderr.decode(errors="ignore").strip(),
                "time": elapsed,
                "success": success
            }
            if success:
                passed += 1
            results.append(record)
        except subprocess.TimeoutExpired:
            results.append({
                "input": input_data,
                "expected": expected_output.strip(),
                "actual": "(timeout)",
                "stderr": "",
                "time": None,
                "success": False
            })
        except Exception as e:
            results.append({
                "input": input_data,
                "expected": expected_output.strip(),
                "actual": None,
                "stderr": str(e),
                "time": None,
                "success": False
            })

    score_pct = round((passed / total) * 100, 2) if total > 0 else 0.0
    return {"status": "done", "passed": passed, "total": total, "results": results, "score": score_pct}

# ---------- Performance measurement ----------
def measure_performance(compile_info: Dict[str, Any], samples: int = 3, timeout=2) -> Dict[str, Any]:
    if not compile_info.get("binary_path"):
        return {"avg_time": None, "comment": "No binary to test."}
    binary = compile_info["binary_path"]
    times = []
    for _ in range(samples):
        try:
            start = time.time()
            subprocess.run([binary], input=b"", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, cwd=os.path.dirname(binary))
            times.append(time.time() - start)
        except subprocess.TimeoutExpired:
            return {"avg_time": None, "comment": "Execution timed out during performance test."}
        except Exception as e:
            logger.warning("Performance run failed: %s", e)
            return {"avg_time": None, "comment": f"Performance run error: {e}"}
    avg = round(sum(times) / len(times), 6)
    comment = "Excellent performance." if avg < 0.05 else ("Acceptable performance." if avg < 0.5 else "Consider optimizing code efficiency.")
    return {"avg_time": avg, "comment": comment}

# ---------- Score calculation (agent-only) ----------
def calculate_score(compile_info: Dict[str, Any], static_info: Dict[str, Any], test_info: Dict[str, Any], perf_info: Dict[str, Any]) -> float:
    # weights are intentionally explicit and fixed (no LLM influence)
    compile_score = 1.0 if compile_info.get("status") == "success" else 0.0
    static_penalty = 0.0
    if static_info.get("count", 0) > 0:
        # each issue reduces static score (capped)
        static_penalty = min(0.5, 0.05 * static_info.get("count", 0))
    static_score = 1.0 - static_penalty
    test_score = (test_info.get("score", 0) / 100.0)  # convert percent to 0..1
    perf_score = 1.0 if perf_info.get("avg_time") is not None and perf_info.get("avg_time") < 0.5 else 0.6 if perf_info.get("avg_time") is not None else 0.0

    # weighted combination
    final = 0.25 * compile_score + 0.45 * test_score + 0.15 * static_score + 0.15 * perf_score
    final_pct = round(final * 100, 2)
    return final_pct

# ---------- PDF report builder ----------
def create_pdf_report(report_text: str, evaluation_json: Dict[str, Any]) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("<b>C Autograder Evaluation Report</b>", styles["Title"]))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(report_text.replace("\n", "<br/>"), styles["BodyText"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("<b>Machine-readable Evaluation (JSON):</b>", styles["Heading3"]))
    pretty_json = json.dumps(evaluation_json, indent=2)
    # break JSON into chunks for Paragraphs
    for chunk in pretty_json.splitlines():
        elements.append(Paragraph(chunk.replace(" ", "&nbsp;"), styles["Code"]))
    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

# ---------- Main pipeline ----------
def run_grader_pipeline(code_text: str, tests: List[str], llm_reporter=None) -> Dict[str, Any]:
    # 1. compile
    compile_info = compile_code(code_text)

    # 2. static analysis (pass path to source file)
    source_path = os.path.join(compile_info.get("temp_dir", ""), "submission.c") if compile_info.get("temp_dir") else None
    static_info = analyze_code_static(source_path) if source_path else {"issues": ["no source file"], "count": 1}

    # 3. tests
    test_info = run_test_cases(compile_info, tests or [])

    # 4. performance
    perf_info = measure_performance(compile_info)

    # 5. final score (agent computed)
    final_score = calculate_score(compile_info, static_info, test_info, perf_info)

    # 6. prepare evaluation JSON to send to LLM for a report (LLM only receives evaluation JSON)
    evaluation = {
        "code_summary": {"length_lines": len(code_text.splitlines())},
        "compile": {k: compile_info.get(k) for k in ("status", "stdout", "stderr", "returncode")},
        "static": static_info,
        "test": test_info,
        "perf": perf_info,
        "final_score": final_score
    }

    llm_report = None
    try:
        if llm_reporter:
            # IMPORTANT: only pass the evaluation JSON (no hidden grading logic). The LLM writes a textual report.
            llm_report = llm_reporter(evaluation)
    except Exception as e:
        logger.exception("LLM report generation failed: %s", e)
        llm_report = f"(LLM report generation failed: {e})"

    # 7. Build PDF that contains the LLM report (or fallback text) + evaluation JSON
    try:
        report_text = llm_report or "No LLM report generated."
        pdf_bytes = create_pdf_report(report_text, evaluation)
    except Exception as e:
        logger.exception("PDF generation failed: %s", e)
        pdf_bytes = None

    # 8. cleanup
    try:
        if compile_info and compile_info.get("temp_dir"):
            shutil.rmtree(compile_info["temp_dir"], ignore_errors=True)
    except Exception as e:
        logger.warning("Cleanup failed: %s", e)

    ret = {
        "code": code_text,
        "compile": compile_info,
        "static": static_info,
        "test": test_info,
        "perf": perf_info,
        "score": final_score,
        "report": llm_report,
        "final_score": final_score,
        "pdf_bytes": pdf_bytes,
        "evaluation_json": evaluation
    }
    return ret
