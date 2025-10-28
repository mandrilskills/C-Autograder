import asyncio
import subprocess
import time
import uuid
from pathlib import Path
from typing import TypedDict, Dict, Any, Optional
from langgraph.graph import StateGraph, END


WORK_DIR = Path("/tmp")  # cloud-safe
WORK_DIR.mkdir(exist_ok=True)


class GraderState(TypedDict, total=False):
    compile: dict
    static: dict
    test: dict
    perf: dict
    final: dict


# ---------- subprocess helper ----------
async def run_subprocess(cmd, input_data=None, timeout=None, cwd=None):
    loop = asyncio.get_event_loop()

    def _run():
        try:
            return subprocess.run(
                cmd,
                input=input_data or "",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(cmd, 1, "", "❌ Timeout (possibly waiting for input).")

    return await loop.run_in_executor(None, _run)


# ---------- Agents ----------
async def compile_agent(state: GraderState, config: Dict[str, Any] = None):
    conf = (config or {}).get("configurable", {})
    submission_id = conf.get("submission_id", f"run_{uuid.uuid4().hex[:6]}")
    code = conf.get("source_code", "")

    base_dir = WORK_DIR / f"{submission_id}_{uuid.uuid4().hex[:8]}"
    base_dir.mkdir(parents=True, exist_ok=True)

    src = base_dir / "main.c"
    exe = base_dir / "a.out"
    src.write_text(code)

    cmd = ["gcc", "-std=c11", str(src), "-o", str(exe), "-Wall", "-Wextra"]
    proc = await run_subprocess(cmd, timeout=10)
    success = proc.returncode == 0
    stderr_text = proc.stderr.strip()

    if "undefined reference to `main`" in stderr_text or "undefined reference to `main'" in stderr_text:
        stderr_text = "❌ Linker error: no main() found."

    return {
        "compile": {
            "success": success,
            "stderr": stderr_text,
            "run_dir": str(base_dir),
            "score": 1.0 if success else 0.0,
        }
    }


async def static_agent(state: GraderState, config: Dict[str, Any] = None):
    if not state.get("compile", {}).get("success"):
        return {"static": {"success": False, "score": 0.0, "issues": ["Skipped (compile failed)."]}}

    run_dir = Path(state["compile"]["run_dir"])
    src = run_dir / "main.c"
    issues = []
    try:
        cpp = subprocess.run(
            ["cppcheck", "--enable=warning,style,performance", str(src)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        out = cpp.stdout + cpp.stderr
        for line in out.splitlines():
            if line.strip() and not line.startswith("Checking"):
                issues.append(line.strip())
    except Exception as e:
        issues.append(f"Static analysis error: {e}")

    score = max(0.0, 1.0 - 0.05 * len(issues))
    return {"static": {"success": True, "score": score, "issues": issues}}


async def test_agent(state: GraderState, config: Dict[str, Any] = None):
    conf = (config or {}).get("configurable", {})
    tests = conf.get("tests", [])
    run_dir = Path(state["compile"]["run_dir"])
    exe = run_dir / "a.out"

    results = []
    passed = 0
    if not tests:
        return {"test": {"success": True, "score": 0, "results": []}}

    for t in tests:
        proc = await run_subprocess([str(exe)], input_data=t["input"], timeout=3)
        out = proc.stdout.strip()
        ok = out == t["output"].strip()
        results.append({"input": t["input"], "expected": t["output"], "output": out, "passed": ok})
        if ok:
            passed += 1

    score = passed / len(tests)
    return {"test": {"success": True, "score": score, "results": results, "passed": passed, "total": len(tests)}}


async def performance_agent(state: GraderState, config: Dict[str, Any] = None):
    if not state.get("compile", {}).get("success"):
        return {"perf": {"success": False, "score": 0.0, "avg_time": 0.0}}

    run_dir = Path(state["compile"]["run_dir"])
    exe = run_dir / "a.out"
    sample_input = "0 0\n"

    times = []
    for _ in range(3):
        start = time.perf_counter()
        await run_subprocess([str(exe)], input_data=sample_input, timeout=3)
        times.append(time.perf_counter() - start)
    avg = sum(times) / len(times) if times else 0.0
    score = 1.0 if avg < 0.1 else (0.7 if avg < 1.0 else 0.3)
    return {"perf": {"success": True, "score": score, "avg_time": avg}}


def orchestrate(state: GraderState, config: Dict[str, Any] = None):
    weights = {"compile": 0.25, "test": 0.4, "static": 0.2, "perf": 0.15}
    if not state.get("compile", {}).get("success"):
        return {"final": {"score": 0.0}}
    total = sum(w * state.get(k, {}).get("score", 0.0) for k, w in weights.items())
    return {"final": {"score": total}}


# ---------- Feedback ----------
def feedback(result: GraderState):
    fb = {"final_score": round(result.get("final", {}).get("score", 0.0) * 100, 2), "sections": []}

    compile_res = result.get("compile", {})
    test_res = result.get("test", {})
    static_res = result.get("static", {})
    perf_res = result.get("perf", {})

    fb["sections"].append({
        "section": "Compilation",
        "score": round(compile_res.get("score", 0) * 100, 1),
        "text": "✅ Compiled successfully." if compile_res.get("success") else compile_res.get("stderr", "")
    })

    if test_res:
        fb["sections"].append({
            "section": "Functional Tests",
            "score": round(test_res.get("score", 0) * 100, 1),
            "text": f"Passed {test_res.get('passed', 0)}/{test_res.get('total', 0)} tests."
        })

    if static_res:
        issues = static_res.get("issues", [])
        fb["sections"].append({
            "section": "Static Analysis",
            "score": round(static_res.get("score", 0) * 100, 1),
            "text": "✅ No issues." if not issues else f"⚠️ {len(issues)} issue(s):\n" + "\n".join(issues[:5])
        })

    if perf_res:
        fb["sections"].append({
            "section": "Performance",
            "score": round(perf_res.get("score", 0) * 100, 1),
            "text": f"⏱ Avg runtime: {perf_res.get('avg_time', 0.0):.4f}s"
        })

    fb["conclusion"] = (
        "🏆 Excellent! Everything works perfectly." if fb["final_score"] >= 80
        else "⚙️ Needs improvement — check logic or performance."
    )
    return fb


# ---------- Graph Builder ----------
def build_grader_graph():
    g = StateGraph(GraderState)
    g.add_node("compile", compile_agent)
    g.add_node("static", static_agent)
    g.add_node("test", test_agent)
    g.add_node("perf", performance_agent)
    g.add_node("orchestrate", orchestrate)
    g.set_entry_point("compile")

    def after_compile(state: GraderState):
        if state.get("compile", {}).get("success"):
            return "next"
        return "end"

    g.add_conditional_edges("compile", after_compile, {"next": "static", "end": "orchestrate"})
    g.add_edge("static", "test")
    g.add_edge("test", "perf")
    g.add_edge("perf", "orchestrate")
    g.add_edge("orchestrate", END)
    return g.compile()
