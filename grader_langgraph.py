"""
grader_langgraph.py

Enhanced version:
- Cleans up compiled binaries and temp dirs after grading
- Generates human-readable PDF report using reportlab
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel
import tempfile
import subprocess
import os
import shutil
import time
import logging
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class GraderState(BaseModel):
    code: str
    tests: List[str] = []
    compile: Optional[Dict[str, Any]] = None
    static: Optional[Dict[str, Any]] = None
    test: Optional[Dict[str, Any]] = None
    perf: Optional[Dict[str, Any]] = None
    report: Optional[str] = None
    final_score: Optional[float] = None
    messages: Optional[List[Dict[str, Any]]] = None


###############################################################################
# Utility: compile code in a temporary directory
###############################################################################
def compile_c_code(code_text: str, timeout_seconds: int = 10) -> Dict[str, Any]:
    result = {"status": "error", "binary_path": None, "stdout": "", "stderr": "", "returncode": None, "temp_dir": None}
    tmpdir = tempfile.mkdtemp(prefix="grader_compile_")
    src_path = os.path.join(tmpdir, "submission.c")
    bin_path = os.path.join(tmpdir, "submission_bin")
    result["temp_dir"] = tmpdir

    try:
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(code_text)

        proc = subprocess.run(["gcc", src_path, "-o", bin_path], capture_output=True, text=True, timeout=timeout_seconds)
        result["stdout"] = proc.stdout or ""
        result["stderr"] = proc.stderr or ""
        result["returncode"] = proc.returncode
        if proc.returncode == 0 and os.path.exists(bin_path):
            result["status"] = "success"
            result["binary_path"] = bin_path
        else:
            result["status"] = "error"
    except subprocess.TimeoutExpired:
        result["stderr"] = f"Compilation timed out after {timeout_seconds}s."
        result["status"] = "error"
    except Exception as e:
        result["stderr"] = str(e)
        result["status"] = "error"

    return result


def run_binary_with_input(bin_path: str, input_data: str, timeout_seconds: int = 3) -> Dict[str, Any]:
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
    return result


def cleanup_temp_dir(path: str):
    """Delete the temp directory safely."""
    try:
        if path and os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
            logger.info(f"Cleaned up temp directory: {path}")
    except Exception as e:
        logger.warning(f"Failed to clean up temp dir {path}: {e}")


###############################################################################
# Agents
###############################################################################
def compile_agent(state: GraderState) -> Dict[str, Any]:
    logger.info("Compiling code...")
    compile_res = compile_c_code(state.code)
    return {"compile": compile_res}


def static_agent(state: GraderState) -> Dict[str, Any]:
    code = state.code or ""
    issues = []
    if "system(" in code:
        issues.append("❌ Use of system() detected — potential security risk.")
    if "gets(" in code:
        issues.append("❌ Use of gets() detected — unsafe input handling.")
    if "main(" not in code:
        issues.append("⚠️ No main() found — program may not run correctly.")
    lines = len(code.splitlines())
    return {"static": {"issues": issues, "lines": lines}}


def test_agent(state: GraderState) -> Dict[str, Any]:
    compile_info = state.compile or {}
    if compile_info.get("status") != "success":
        return {"test": {"status": "skipped", "reason": "Compilation failed", "results": []}}

    bin_path = compile_info["binary_path"]
    results = []
    passed = 0
    for t in state.tests:
        if "::" in t:
            inp, exp = t.split("::", 1)
        else:
            inp, exp = t, ""
        res = run_binary_with_input(bin_path, inp.strip())
        out = res.get("stdout", "").strip()
        passed_flag = (out == exp.strip())
        if passed_flag:
            passed += 1
        results.append({"input": inp, "expected": exp, "output": out, "pass": passed_flag})
    total = len(state.tests)
    score = round((passed / total) * 100, 2) if total else 0
    return {"test": {"status": "done", "passed": passed, "total": total, "score": score, "results": results}}


def performance_agent(state: GraderState) -> Dict[str, Any]:
    test_info = state.test or {}
    times = [t.get("meta", {}).get("time") for t in test_info.get("results", []) if t.get("meta")]
    avg_time = round(sum(times) / len(times), 4) if times else None
    return {"perf": {"avg_time": avg_time, "comment": "Program executed efficiently." if avg_time and avg_time < 1 else "Consider optimizing code efficiency."}}


def orchestrate(state: GraderState, llm_reporter=None) -> Dict[str, Any]:
    compile_ok = 1 if (state.compile or {}).get("status") == "success" else 0
    test_score = (state.test or {}).get("score", 0)
    perf_bonus = 5.0
    final_score = round(0.85 * test_score + 0.10 * (100 if compile_ok else 0) + 0.05 * perf_bonus, 2)

    context = {
        "code": state.code,
        "compile": state.compile,
        "static": state.static,
        "test": state.test,
        "perf": state.perf,
        "score": final_score,
    }

    if llm_reporter:
        try:
            report_text = llm_reporter(context)
        except Exception as e:
            logger.warning(f"LLM reporter failed: {e}")
            report_text = None
    else:
        report_text = generate_human_report(context)

    return {"report": report_text, "final_score": final_score}


def generate_human_report(ctx: Dict[str, Any]) -> str:
    """Fallback report with clear human-readable analysis."""
    lines = [
        "## C Program Evaluation Report",
        "",
        f"**Overall Score:** {ctx.get('score', 'N/A')}/100",
        "",
        "### Compilation:",
        f"Status: {ctx.get('compile', {}).get('status', 'Unknown')}",
        f"Compiler Output: {ctx.get('compile', {}).get('stderr', '')}",
        "",
        "### Static Analysis:",
        f"Issues: {ctx.get('static', {}).get('issues', [])}",
        "",
        "### Functional Tests:",
        f"Passed: {ctx.get('test', {}).get('passed', 0)} / {ctx.get('test', {}).get('total', 0)}",
        "",
        "### Performance:",
        f"{ctx.get('perf', {}).get('comment', '')}",
        "",
        "### Final Judgement:",
        "The code demonstrates functional correctness with areas of improvement in code safety and efficiency."
    ]
    return "\n".join(lines)


###############################################################################
# PDF Report Generator
###############################################################################
def create_pdf_report(report_text: str, results: Dict[str, Any]) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    justified = ParagraphStyle(
        "Justify",
        parent=styles["BodyText"],
        alignment=TA_JUSTIFY,
        leading=16,
    )

    story.append(Paragraph("<b>C Programming Evaluation Report</b>", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph(report_text.replace("\n", "<br/>"), justified))
    story.append(Spacer(1, 24))

    if "final_score" in results:
        story.append(Paragraph(f"<b>Final Score:</b> {results['final_score']}/100", styles["Heading3"]))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


###############################################################################
# Pipeline runner
###############################################################################
def run_grader_pipeline(code_text: str, tests: Optional[List[str]] = None, llm_reporter=None) -> Dict[str, Any]:
    state = GraderState(code=code_text, tests=tests or [])
    compile_out = compile_agent(state)
    state.compile = compile_out.get("compile")

    static_out = static_agent(state)
    state.static = static_out.get("static")

    test_out = test_agent(state)
    state.test = test_out.get("test")

    perf_out = performance_agent(state)
    state.perf = perf_out.get("perf")

    orch_out = orchestrate(state, llm_reporter)
    state.report = orch_out.get("report")
    state.final_score = orch_out.get("final_score")

    # Cleanup temp directory
    tmpdir = (state.compile or {}).get("temp_dir")
    cleanup_temp_dir(tmpdir)

    return state.dict()
