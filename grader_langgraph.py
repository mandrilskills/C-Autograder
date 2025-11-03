# grader_langgraph.py
import os
import tempfile
import subprocess
import time
import json
import shutil
import logging
from io import BytesIO
from typing import Any, Dict, List, Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------- Diagnostics ----------------
def run_diagnostics() -> Dict[str, Any]:
    """
    Check presence of gcc, cppcheck and environment variables for Gemini.
    Returns a dict of booleans + debug strings.
    """
    diag = {"gcc": False, "cppcheck": False, "genai_env": False, "details": {}}
    diag["details"]["which_gcc"] = shutil.which("gcc")
    diag["details"]["which_cppcheck"] = shutil.which("cppcheck")
    diag["gcc"] = bool(diag["details"]["which_gcc"])
    diag["cppcheck"] = bool(diag["details"]["which_cppcheck"])
    diag["details"]["env_GENAI_API_KEY"] = bool(os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    diag["genai_env"] = diag["details"]["env_GENAI_API_KEY"]
    return diag

# ----------------- Test normalization -----------------
def _try_parse_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None

def normalize_tests_block(tests_raw: Any) -> List[Dict[str, str]]:
    """
    Accept flexible formats:
    - JSON string/list/dict: {"tests":[{"input":"...","expected":"..."}]}
    - Multiline text with "input::expected" or single-line inputs.
    - List-like text (one test per line).
    Returns list of {'input': str, 'expected': str}
    """
    if not tests_raw:
        return []

    # If already list/dict
    if isinstance(tests_raw, list):
        out = []
        for t in tests_raw:
            if isinstance(t, dict):
                out.append({"input": str(t.get("input", "")), "expected": str(t.get("expected", ""))})
            else:
                out.append({"input": str(t), "expected": ""})
        return out

    # If string, try JSON parse first
    if isinstance(tests_raw, str):
        js = _try_parse_json(tests_raw)
        if js:
            # accept {"tests": [...] } or plain list
            if isinstance(js, dict) and "tests" in js and isinstance(js["tests"], list):
                return normalize_tests_block(js["tests"])
            if isinstance(js, list):
                return normalize_tests_block(js)
            # if single dict with input/expected
            if isinstance(js, dict) and ("input" in js or "expected" in js):
                return [{"input": str(js.get("input", "")), "expected": str(js.get("expected", ""))}]
        # fallback: parse lines
        lines = [ln.strip() for ln in tests_raw.splitlines() if ln.strip()]
        out = []
        for ln in lines:
            if "::" in ln:
                a, b = ln.split("::", 1)
                out.append({"input": a.strip(), "expected": b.strip()})
            else:
                out.append({"input": ln, "expected": ""})
        return out

    # fallback
    return []

# ----------------- Compilation -----------------
def compile_code_to_binary(code_text: str, temp_dir: Optional[str]=None) -> Dict[str, Any]:
    td = temp_dir or tempfile.mkdtemp(prefix="grader_")
    src = os.path.join(td, "submission.c")
    with open(src, "w") as f:
        f.write(code_text)
    binary = os.path.join(td, "submission_bin")
    # Compile
    try:
        proc = subprocess.run(["gcc", src, "-o", binary, "-std=c11", "-Wall", "-O2"], capture_output=True, text=True, cwd=td, timeout=20)
        status = "success" if proc.returncode == 0 else "error"
        # ensure executable bit if created
        if os.path.exists(binary):
            try:
                os.chmod(binary, 0o755)
            except Exception:
                pass
        return {"status": status, "stdout": proc.stdout, "stderr": proc.stderr, "binary": binary if status=="success" else None, "temp_dir": td, "returncode": proc.returncode}
    except Exception as e:
        return {"status": "error", "stdout": "", "stderr": str(e), "binary": None, "temp_dir": td, "returncode": -1}

# ----------------- Static analysis -----------------
def run_cppcheck(src_path: str) -> Dict[str, Any]:
    issues = []
    cppcheck_path = shutil.which("cppcheck")
    if not cppcheck_path:
        return {"available": False, "issues": ["cppcheck not installed"]}

    try:
        proc = subprocess.run([cppcheck_path, "--enable=all", src_path], capture_output=True, text=True, timeout=12)
        out = proc.stdout + proc.stderr
        for line in out.splitlines():
            line=line.strip()
            if not line:
                continue
            if line.startswith("Checking"):
                continue
            issues.append(line)
        return {"available": True, "issues": issues}
    except Exception as e:
        return {"available": True, "issues": [f"cppcheck error: {e}"]}

# ----------------- Run tests (safe) -----------------
def run_tests_on_binary(binary_path: str, tests: List[Dict[str,str]], timeout_per_test: int = 5) -> Dict[str, Any]:
    results = []
    passed = 0
    total = len(tests)
    if not binary_path:
        return {"status":"error", "results": [], "passed": 0, "total": total, "score": 0}

    for t in tests:
        inp = t.get("input","")
        expected = t.get("expected","").strip()
        try:
            start = time.time()
            proc = subprocess.run([binary_path], input=inp.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_per_test)
            elapsed = time.time() - start
            out = proc.stdout.decode(errors="ignore").strip()
            stderr = proc.stderr.decode(errors="ignore").strip()
            # If expected is empty treat test as manual verification (pass if program exited)
            if expected == "":
                success = proc.returncode == 0
            else:
                success = out == expected
            comment = "OK" if success else ("mismatch" if expected!="" else ("non-zero exit" if proc.returncode!=0 else "OK"))
            results.append({"input": inp, "expected": expected, "actual": out, "stderr": stderr, "success": success, "time": round(elapsed,4), "comment": comment})
            if success:
                passed += 1
        except subprocess.TimeoutExpired:
            results.append({"input": inp, "expected": expected, "actual": "(timeout)", "stderr": "", "success": False, "time": None, "comment": f"timed out after {timeout_per_test}s"})
        except Exception as e:
            results.append({"input": inp, "expected": expected, "actual": "", "stderr": str(e), "success": False, "time": None, "comment": "runtime error"})
    score = round((passed/total*100),2) if total>0 else 0.0
    return {"status":"done","results":results,"passed":passed,"total":total,"score":score}

# ----------------- Performance (simple) -----------------
def measure_perf(binary_path: str) -> Dict[str,Any]:
    if not binary_path:
        return {"avg_time": None, "comment": "no binary"}
    times=[]
    for _ in range(3):
        try:
            start=time.time()
            subprocess.run([binary_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
            times.append(time.time()-start)
        except Exception:
            return {"avg_time": None, "comment": "perf run failed or timed out"}
    avg=round(sum(times)/len(times),4)
    return {"avg_time": avg, "comment": ("fast" if avg<0.1 else "moderate" if avg<0.5 else "slow")}

# ----------------- PDF builder -----------------
def build_pdf(report_text: str, evaluation: Dict[str,Any]) -> bytes:
    buf=BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=A4)
    styles=getSampleStyleSheet()
    elems=[Paragraph("C Autograder Report", styles["Title"]), Spacer(1,8), Paragraph(report_text.replace("\n","<br/>"), styles["Normal"]), Spacer(1,8), Paragraph("Evaluation JSON", styles["Heading3"]), Paragraph(json.dumps(evaluation, indent=2).replace(" ", "&nbsp;"), styles["Code"])]
    doc.build(elems)
    return buf.getvalue()

# ----------------- Main pipeline -----------------
def run_grader_pipeline(code_text: str, tests_raw: Any, llm_reporter=None, per_test_timeout: int = 5) -> Dict[str,Any]:
    # Diagnostics at start
    diag = run_diagnostics()
    # compile
    compile_info = compile_code_to_binary(code_text)
    src_path = os.path.join(compile_info.get("temp_dir",""), "submission.c")
    # static
    static_info = run_cppcheck(src_path) if os.path.exists(src_path) else {"available": False, "issues": ["source missing"]}
    # normalize tests
    tests = normalize_tests_block(tests_raw)
    # run tests (with safe timeout)
    test_info = run_tests_on_binary(compile_info.get("binary"), tests, timeout_per_test=per_test_timeout)
    # perf
    perf_info = measure_perf(compile_info.get("binary"))
    # score
    compile_ok = 1 if compile_info.get("status")=="success" else 0
    static_penalty = min(0.5, 0.05 * len(static_info.get("issues", []))) if static_info.get("available", True) else 0.0
    static_score = max(0, 1.0 - static_penalty)
    test_score = test_info.get("score", 0)/100.0
    perf_score = 1.0 if perf_info.get("avg_time") and perf_info.get("avg_time")<0.5 else 0.6
    final_score = round((0.25*compile_ok + 0.45*test_score + 0.15*static_score + 0.15*perf_score)*100,2)

    evaluation = {"diagnostics": diag, "compile": compile_info, "static": static_info, "test": test_info, "perf": perf_info, "final_score": final_score}

    # LLM report
    report_text = None
    if llm_reporter:
        try:
            report_text = llm_reporter(evaluation)
        except Exception as e:
            report_text = f"(LLM report generation failed: {e})"

    pdf_bytes = build_pdf(report_text or "No report generated.", evaluation)
    # cleanup
    try:
        if compile_info.get("temp_dir"):
            shutil.rmtree(compile_info["temp_dir"], ignore_errors=True)
    except Exception:
        pass

    return {"compile": compile_info, "static": static_info, "test": test_info, "perf": perf_info, "final_score": final_score, "report": report_text, "pdf_bytes": pdf_bytes}
