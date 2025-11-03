"""
grader_langgraph.py
--------------------------------
Core grading logic for the C Autograder app.
Handles:
- Compilation
- Static code analysis
- Test execution
- Performance measurement
- Final scoring
- LLM report integration
- PDF report generation
"""

import os
import subprocess
import tempfile
import time
import shutil
import logging
from io import BytesIO
from typing import List, Dict, Any
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =====================
#   Compilation Stage
# =====================

def compile_code(code_text: str) -> Dict[str, Any]:
    """Compile C code and return compilation metadata."""
    temp_dir = tempfile.mkdtemp(prefix="grader_compile_")
    source_path = os.path.join(temp_dir, "submission.c")
    binary_path = os.path.join(temp_dir, "submission_bin")

    with open(source_path, "w") as f:
        f.write(code_text)

    compile_cmd = ["gcc", source_path, "-o", binary_path]
    result = subprocess.run(compile_cmd, capture_output=True, text=True)
    compile_info = {
        "status": "success" if result.returncode == 0 else "error",
        "binary_path": binary_path if result.returncode == 0 else None,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
        "temp_dir": temp_dir,
    }
    return compile_info


# =====================
#   Static Analysis
# =====================

def analyze_code_static(code_text: str) -> Dict[str, Any]:
    """Perform static analysis for unsafe or suspicious patterns."""
    issues = []
    if "gets(" in code_text:
        issues.append("Use of unsafe function gets()")
    if "system(" in code_text:
        issues.append("Use of system() call")
    if "while(1)" in code_text or "for(;;)" in code_text:
        issues.append("Potential infinite loop detected")

    return {"issues": issues, "lines": len(code_text.splitlines())}


# =====================
#   Testing Stage
# =====================

def run_test_cases(compile_info: Dict[str, Any], tests: List[str]) -> Dict[str, Any]:
    """Run provided test cases on compiled binary."""
    if not compile_info.get("binary_path"):
        return {"status": "error", "passed": 0, "total": len(tests), "results": [], "score": 0}

    binary_path = compile_info["binary_path"]
    passed = 0
    total = len(tests)
    results = []

    for case in tests:
        if "::" not in case:
            continue
        input_data, expected_output = case.split("::", 1)
        try:
            start = time.time()
            proc = subprocess.run(
                [binary_path],
                input=input_data.encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=3,
            )
            elapsed = round(time.time() - start, 4)
            actual_output = proc.stdout.decode().strip()
            success = actual_output == expected_output.strip()
            results.append({
                "input": input_data,
                "expected": expected_output.strip(),
                "actual": actual_output,
                "time": elapsed,
                "success": success,
            })
            if success:
                passed += 1
        except subprocess.TimeoutExpired:
            results.append({
                "input": input_data,
                "expected": expected_output,
                "actual": "(timeout)",
                "time": None,
                "success": False,
            })

    score = round((passed / total) * 100, 2) if total > 0 else 0
    return {"status": "done", "passed": passed, "total": total, "results": results, "score": score}


# =====================
#   Performance Stage
# =====================

def measure_performance(compile_info: Dict[str, Any]) -> Dict[str, Any]:
    """Run a quick performance timing on the binary."""
    if not compile_info.get("binary_path"):
        return {"avg_time": None, "comment": "No binary to test."}

    binary = compile_info["binary_path"]
    try:
        start = time.time()
        subprocess.run([binary], input=b"", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
        elapsed = round(time.time() - start, 5)
        comment = (
            "Excellent performance." if elapsed < 0.05 else
            "Acceptable performance." if elapsed < 0.5 else
            "Consider optimizing code efficiency."
        )
        return {"avg_time": elapsed, "comment": comment}
    except subprocess.TimeoutExpired:
        return {"avg_time": None, "comment": "Execution took too long (timeout)."}


# =====================
#   Scoring Logic
# =====================

def calculate_score(compile_info, static_info, test_info, perf_info) -> float:
    """Weighted score based on compilation, static quality, correctness, and performance."""
    score = 0.0
    if compile_info["status"] == "success":
        score += 10
    if not static_info["issues"]:
        score += 5
    score += test_info.get("score", 0) * 0.85
    if perf_info.get("avg_time") is not None:
        score += 5
    return round(min(score, 100), 2)


# =====================
#   PDF Report Builder
# =====================

def create_pdf_report(report_text: str, results: Dict[str, Any]) -> bytes:
    """Create a clean, human-readable PDF report."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    elements = []
    elements.append(Paragraph("<b>C Autograder Evaluation Report</b>", styles["Title"]))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(report_text.replace("\n", "<br/>"), styles["BodyText"]))
    elements.append(Spacer(1, 12))

    final_score = results.get("final_score", 0)
    elements.append(Paragraph(f"<b>Final Score:</b> {final_score}/100", styles["BodyText"]))

    test_info = results.get("test", {})
    if test_info.get("results"):
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("<b>Test Case Results:</b>", styles["Heading2"]))
        for i, t in enumerate(test_info["results"], start=1):
            color = "green" if t["success"] else "red"
            line = f"<font color='{color}'>Test {i}: {t['input']} → Expected: {t['expected']}, Got: {t['actual']}</font>"
            elements.append(Paragraph(line, styles["BodyText"]))
            elements.append(Spacer(1, 4))

    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data


# =====================
#   Main Grading Flow
# =====================

def run_grader_pipeline(code_text: str, tests: List[str], llm_reporter=None) -> Dict[str, Any]:
    """Complete grading pipeline integrating all stages."""
    compile_info = compile_code(code_text)
    static_info = analyze_code_static(code_text)
    test_info = run_test_cases(compile_info, tests)
    perf_info = measure_performance(compile_info)
    final_score = calculate_score(compile_info, static_info, test_info, perf_info)

    llm_report = None
    try:
        if llm_reporter:
            llm_report = llm_reporter({
                "code": code_text,
                "compile": compile_info,
                "static": static_info,
                "test": test_info,
                "perf": perf_info,
                "score": final_score
            })
    except Exception as e:
        logger.error(f"LLM report generation failed: {e}")
        llm_report = f"(Automated fallback: LLM report could not be generated: {e})"

    # Cleanup temporary binary directory
    try:
        if compile_info and "temp_dir" in compile_info:
            shutil.rmtree(compile_info["temp_dir"], ignore_errors=True)
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")

    return {
        "code": code_text,
        "compile": compile_info,
        "static": static_info,
        "test": test_info,
        "perf": perf_info,
        "score": final_score,
        "report": llm_report or "No LLM report generated.",
        "final_score": final_score,
    }
