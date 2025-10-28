import asyncio
import subprocess
import time
from pathlib import Path
from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph, END

# ====== Setup ======
WORK_DIR = Path("runs")
WORK_DIR.mkdir(exist_ok=True)

# ====== Define State Schema ======
class GraderState(TypedDict, total=False):
    compile: dict
    static: dict
    perf: dict
    final: dict

# ====== Windows/Linux-safe subprocess helper ======
async def run_subprocess(cmd, input_data=None, timeout=None, cwd=None):
    """Run a subprocess asynchronously with optional stdin input."""
    loop = asyncio.get_event_loop()

    def _run():
        return subprocess.run(
            cmd,
            input=input_data if input_data else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
            cwd=cwd,  # Ensures working directory is correct for cloud
        )

    return await loop.run_in_executor(None, _run)

# ====== AGENTS ======
async def compile_agent(state: GraderState, config: Dict[str, Any]):
    configurable = config.get("configurable", {})
    submission_id = configurable.get("submission_id", "default-id")
    source_code = configurable.get("source_code", "")

    run_dir = WORK_DIR / submission_id
    run_dir.mkdir(exist_ok=True)
    src = run_dir / "main.c"
    src.write_text(source_code)
    exe = run_dir / "a.out"

    # Safety check before compilation
    if not src.exists():
        return {
            "compile": {
                "success": False,
                "stderr": "❌ Source file not found.",
                "score": 0.0,
            }
        }

    cmd = ["gcc", "-std=c11", "main.c", "-o", "a.out", "-Wall", "-Wextra"]

    proc = await run_subprocess(cmd, timeout=10, cwd=str(run_dir))
    success = proc.returncode == 0

    return {
        "compile": {
            "success": success,
            "stderr": proc.stderr,
            "stdout": proc.stdout,
            "run_dir": str(run_dir),
            "exe": str(exe),
            "score": 1.0 if success else 0.0,
        }
    }

async def static_agent(state: GraderState, config: Dict[str, Any]):
    """Static code analysis using cppcheck."""
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
            if "error" in line.lower() or "warning" in line.lower():
                issues.append(line.strip())
    except Exception as e:
        issues.append(f"Static analysis error: {str(e)}")

    score = max(0.0, 1.0 - 0.05 * len(issues))
    return {"static": {"success": True, "score": score, "issues": issues}}

async def performance_agent(state: GraderState, config: Dict[str, Any]):
    """Performance check — runs program with a small sample input."""
    run_dir = Path(state["compile"]["run_dir"])
    exe = run_dir / "a.out"
    if not exe.exists():
        return {"perf": {"success": False, "score": 0.0, "avg_time": 0}}

    sample_input = "1 2\n"  # Simple test for runtime measurement
    times = []
    for _ in range(3):
        start = time.perf_counter()
        await run_subprocess(["./a.out"], input_data=sample_input, cwd=str(run_dir))
        times.append(time.perf_counter() - start)

    avg = sum(times) / len(times) if times else 0
    score = 1.0 if avg < 0.1 else (0.7 if avg < 1.0 else 0.3)
    return {"perf": {"success": True, "score": score, "avg_time": avg}}

def orchestrate(state: GraderState, config: Dict[str, Any]):
    """Combine results into a final grade."""
    weights = {"compile": 0.5, "static": 0.25, "perf": 0.25}
    total = 0.0

    if not state.get("compile", {}).get("success", False):
        return {"final": {"score": 0.0}}

    for k, w in weights.items():
        total += w * state.get(k, {}).get("score", 0)

    return {"final": {"score": total}}

# ====== FEEDBACK FORMATTER ======
def feedback(result: GraderState):
    compile_res = result.get("compile", {})
    static_res = result.get("static", {})
    perf_res = result.get("perf", {})
    final_res = result.get("final", {})

    fb = {"final_score": round(final_res.get("score", 0) * 100, 2), "sections": []}

    # Compilation
    fb["sections"].append({
        "section": "Compilation",
        "score": round(compile_res.get("score", 0) * 100, 1),
        "text": (
            "✅ Compiled successfully."
            if compile_res.get("success")
            else f"❌ Compilation failed:\n\n{compile_res.get('stderr', '').strip()}"
        ),
    })

    # Static Analysis
    if compile_res.get("success") and static_res:
        text = "✅ No issues found."
        if static_res.get("issues"):
            issue_list = "\n".join(f"- {i}" for i in static_res["issues"])
            text = f"⚠️ {len(static_res['issues'])} potential issues:\n{issue_list}"
        fb["sections"].append({
            "section": "Static Analysis",
            "score": round(static_res.get("score", 0) * 100, 1),
            "text": text,
        })

    # Performance
    if compile_res.get("success") and perf_res:
        fb["sections"].append({
            "section": "Performance",
            "score": round(perf_res.get("score", 0) * 100, 1),
            "text": f"Avg runtime: {perf_res.get('avg_time', 0):.4f}s",
        })

    # Final Conclusion
    fb["conclusion"] = (
        "✅ Excellent work! All checks passed with high performance."
        if fb["final_score"] > 80
        else (
            "⚠️ Some improvements needed. Review warnings or optimize performance."
            if compile_res.get("success")
            else "❌ Compilation failed. Please fix and retry."
        )
    )

    return fb

# ====== GRAPH BUILDER ======
def build_grader_graph():
    g = StateGraph(GraderState)

    g.add_node("compile", compile_agent)
    g.add_node("static", static_agent)
    g.add_node("perf", performance_agent)
    g.add_node("orchestrate", orchestrate)

    # Graph flow
    g.set_entry_point("compile")

    def route(state: GraderState):
        if state.get("compile", {}).get("success"):
            return "next"
        else:
            return "end"

    g.add_conditional_edges(
        "compile",
        route,
        {"next": "static", "end": "orchestrate"},
    )

    g.add_edge("static", "perf")
    g.add_edge("perf", "orchestrate")
    g.add_edge("orchestrate", END)

    return g.compile()
