# grader_langgraph.py (Flexible Test Case Evaluation)
import os, json, subprocess, tempfile, time, shutil, logging
from typing import Any, Dict, List, Optional
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ----------- Utilities -----------
def _try_parse_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None

def normalize_tests(test_block: Any) -> List[Dict[str, str]]:
    """
    Accepts test_block in any flexible format:
      - String (multiline)
      - JSON list or dict
      - Raw list
    Returns unified list of {input, expected} dicts.
    """
    tests = []

    # Case 1: JSON format
    if isinstance(test_block, str):
        js = _try_parse_json(test_block)
        if js:
            test_block = js

    # Case 2: If it's a dict with key 'tests'
    if isinstance(test_block, dict) and "tests" in test_block:
        test_block = test_block["tests"]

    # Case 3: If it's already list of dicts
    if isinstance(test_block, list) and all(isinstance(t, dict) for t in test_block):
        for t in test_block:
            tests.append({
                "input": str(t.get("input", "")),
                "expected": str(t.get("expected", "")).strip()
            })
        return tests

    # Case 4: If it's raw text
    if isinstance(test_block, str):
        for line in test_block.splitlines():
            line = line.strip()
            if not line:
                continue
            if "::" in line:
                parts = line.split("::", 1)
                tests.append({"input": parts[0].strip(), "expected": parts[1].strip()})
            else:
                # Input-only test (no expected)
                tests.append({"input": line, "expected": ""})
        return tests

    # Case 5: Fallback
    if isinstance(test_block, list):
        for item in test_block:
            tests.append({"input": str(item), "expected": ""})

    return tests

# ----------- Core Steps -----------
def compile_code(code: str) -> Dict[str, Any]:
    temp_dir = tempfile.mkdtemp(prefix="grader_")
    src = os.path.join(temp_dir, "main.c")
    with open(src, "w") as f:
        f.write(code)
    exe = os.path.join(temp_dir, "main.out")

    proc = subprocess.run(["gcc", src, "-o", exe, "-std=c11", "-Wall"], capture_output=True, text=True)
    return {
        "status": "success" if proc.returncode == 0 else "error",
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "binary": exe if proc.returncode == 0 else None,
        "temp_dir": temp_dir
    }

def static_analysis(src_path: str) -> Dict[str, Any]:
    issues = []
    try:
        out = subprocess.run(
            ["cppcheck", "--enable=all", src_path],
            capture_output=True, text=True, timeout=10
        )
        for line in (out.stdout + out.stderr).splitlines():
            if line and "Checking" not in line:
                issues.append(line.strip())
    except Exception as e:
        issues.append(f"Static analysis error: {e}")
    return {"count": len(issues), "issues": issues}

def run_tests(binary: str, tests: List[Dict[str, str]], timeout: int = 5) -> Dict[str, Any]:
    """
    Execute compiled binary on each test input.
    Timeout per test is configurable (default 5s).
    Does not crash pipeline on timeout — just marks test as timed out.
    """
    if not binary:
        return {"status": "error", "results": [], "passed": 0, "total": len(tests), "score": 0}

    results, passed = [], 0
    for t in tests:
        inp, exp = t["input"], t.get("expected", "")
        try:
            proc = subprocess.run(
                [binary],
                input=inp.encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout
            )
            out = proc.stdout.decode().strip()
            success = (not exp.strip()) or (out == exp.strip())
            results.append({
                "input": inp,
                "expected": exp,
                "actual": out,
                "stderr": proc.stderr.decode().strip(),
                "success": success,
                "comment": "OK" if success else "Output mismatch"
            })
            if success:
                passed += 1

        except subprocess.TimeoutExpired:
            results.append({
                "input": inp,
                "expected": exp,
                "actual": "(timeout)",
                "stderr": "",
                "success": False,
                "comment": f"Program timed out after {timeout}s (possible infinite loop or missing input)"
            })

        except Exception as e:
            results.append({
                "input": inp,
                "expected": exp,
                "actual": "",
                "stderr": str(e),
                "success": False,
                "comment": "Runtime error"
            })

    total = len(tests)
    score = round((passed / total * 100), 2) if total > 0 else 0
    return {
        "status": "done",
        "passed": passed,
        "total": total,
        "results": results,
        "score": score
    }

def measure_performance(binary: str) -> Dict[str, Any]:
    if not binary:
        return {"avg_time": None, "comment": "No binary to test."}
    times = []
    for _ in range(3):
        start = time.time()
        subprocess.run([binary], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
        times.append(time.time() - start)
    avg = round(sum(times)/len(times), 5)
    comment = "Fast" if avg < 0.1 else "Moderate" if avg < 0.5 else "Slow"
    return {"avg_time": avg, "comment": comment}

def score_calc(c, s, t, p):
    compile_s = 1 if c["status"] == "success" else 0
    static_s = max(0, 1 - (0.05 * s.get("count", 0)))
    test_s = t.get("score", 0) / 100
    perf_s = 1 if p.get("avg_time") and p["avg_time"] < 0.5 else 0.6
    return round((0.25*compile_s + 0.45*test_s + 0.15*static_s + 0.15*perf_s)*100, 2)

def make_pdf(report_text, evaluation):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    elems = [
        Paragraph("C Autograder Report", styles["Title"]),
        Spacer(1, 10),
        Paragraph(report_text.replace("\n", "<br/>"), styles["Normal"]),
        Spacer(1, 10),
        Paragraph("Evaluation JSON", styles["Heading3"]),
        Paragraph(json.dumps(evaluation, indent=2).replace(" ", "&nbsp;"), styles["Code"])
    ]
    doc.build(elems)
    return buf.getvalue()

def run_grader_pipeline(code_text: str, tests_raw: Any, llm_reporter=None):
    compile_info = compile_code(code_text)
    src = os.path.join(compile_info["temp_dir"], "main.c")
    static_info = static_analysis(src)
    tests = normalize_tests(tests_raw)
    test_info = run_tests(compile_info.get("binary"), tests)
    perf_info = measure_performance(compile_info.get("binary"))
    final_score = score_calc(compile_info, static_info, test_info, perf_info)

    evaluation = {
        "compile": compile_info,
        "static": static_info,
        "test": test_info,
        "perf": perf_info,
        "final_score": final_score
    }

    report = None
    if llm_reporter:
        report = llm_reporter(evaluation)

    pdf_bytes = make_pdf(report or "No report.", evaluation)
    shutil.rmtree(compile_info["temp_dir"], ignore_errors=True)

    return {
        "compile": compile_info,
        "static": static_info,
        "test": test_info,
        "perf": perf_info,
        "final_score": final_score,
        "report": report,
        "pdf_bytes": pdf_bytes
    }

