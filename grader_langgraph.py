import asyncio
import subprocess
import time
import uuid
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
    test: dict
    perf: dict
    final: dict


# ====== Safe Subprocess Helper ======
async def run_subprocess(cmd, input_data=None, timeout=3):
    """Run subprocess safely with timeout & dummy input fallback."""
    loop = asyncio.get_event_loop()

    def _run():
        try:
            return subprocess.run(
                cmd,
                input=input_data if input_data else "",  # avoid scanf freeze
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(cmd, 1, "", "❌ Program timed out (possibly waiting for input)")

    return await loop.run_in_executor(None, _run)


# ====== Agents ======
async def compile_agent(state: GraderState, config: Dict[str, Any] = None):
    """Compile the uploaded C source file."""
    configurable = (config or {}).get("configurable", {})
    submission_id = configurable.get("submission_id", f"run_{uuid.uuid4().hex[:6]}")
    source_code = configurable.get("source_code", "")

    # Create unique directory per submission
    run_dir = WORK_DIR / f"{submission_id}_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(exist_ok=True)

    src = run_dir / "main.c"
    src.write_text(source_code)
    exe = run_dir / "a.exe"

    # Delete old exe if exists
    if exe.exists():
        try:
            exe.unlink()
        except Exception:
            pass

    # Compile command
    cmd = ["gcc", "-std=c11", str(src), "-o", str(exe), "-Wall", "-Wextra"]
    proc = await run_subprocess(cmd)
    success = proc.returncode == 0

    return {
        "compile": {
            "success": success,
            "stderr": proc.stderr.strip(),
            "run_dir": str(run_dir),
            "score": 1.0 if success else 0.0
        },
        "submission_id": submission_id
    }


async def static_agent(state: GraderState, config: Dict[str, Any] = None):
    """Run cppcheck static analysis."""
    run_dir = Path(state["compile"]["run_dir"])
    src = run_dir / "main.c"
    issues = []

    try:
        cpp = subprocess.run(
            ["cppcheck", "--enable=warning,style,performance", str(src)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        out = cpp.stdout + cpp.stderr
        for line in out.splitlines():
            if line.strip():
                issues.append(line.strip())
    except Exception as e:
        issues.append(f"Static analysis failed: {e}")

    score = max(0.0, 1.0 - 0.05 * len(issues))  # Slight penalty per issue
    return {"static": {"success": True, "score": score, "issues": issues}}


async def test_agent(state: GraderState, config: Dict[str, Any] = None):
    """Run the compiled program once to ensure it executes properly."""
    run_dir = Path(state["compile"]["run_dir"])
    exe = run_dir / "a.exe"

    proc = await run_subprocess([str(exe)], input_data="0 0\n", timeout=3)
    out = proc.stdout.strip()
    timed_out = "timed out" in proc.stderr.lower()

    score = 0.0 if timed_out else (1.0 if proc.returncode == 0 else 0.5)
    return {
        "test": {
            "success": not timed_out,
            "score": score,
            "stdout": out,
            "stderr": proc.stderr.strip(),
            "timed_out": timed_out
        }
    }


async def performance_agent(state: GraderState, config: Dict[str, Any] = None):
    """Measure average execution time for performance scoring."""
    run_dir = Path(state["compile"]["run_dir"])
    exe = run_dir / "a.exe"

    times = []
    for _ in range(3):
        start = time.perf_counter()
        proc = await run_subprocess([str(exe)], input_data="0 0\n", timeout=3)
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    avg = sum(times) / len(times) if times else 0
    score = 1.0 if avg < 0.1 else (0.7 if avg < 1.0 else 0.3)
    return {"perf": {"success": True, "score": score, "avg_time": avg}}


def orchestrate(state: GraderState, config: Dict[str, Any] = None):
    """Combine scores into a final weighted score."""
    weights = {"compile": 0.3, "static": 0.2, "test": 0.3, "perf": 0.2}
    total = 0.0

    if not state.get("compile", {}).get("success", False):
        for k in ["static", "test", "perf"]:
            state[k] = {"score": 0.0}
        return {"final": {"score": 0.0}}

    for k, w in weights.items():
        total += w * state.get(k, {}).get("score", 0.0)
    return {"final": {"score": total}}


# ====== Feedback Formatter ======
def feedback(result: GraderState):
    """Create readable feedback summary."""
    compile_res = result.get("compile", {})
    static_res = result.get("static", {})
    test_res = result.get("test", {})
    perf_res = result.get("perf", {})
    final_res = result.get("final", {})

    fb = {"final_score": round(final_res.get("score", 0) * 100, 2), "sections": []}

    # --- Compilation ---
    fb["sections"].append({
        "section": "Compilation",
        "score": round(compile_res.get("score", 0) * 100, 1),
        "text": "✅ Compiled successfully."
        if compile_res.get("success")
        else f"❌ Compilation failed:\n\n{compile_res.get('stderr', 'Unknown error')}"
    })

    # --- Static Analysis ---
    if static_res:
        if static_res.get("issues"):
            issue_text = "\n".join(static_res["issues"][:5])
            text = f"⚠️ {len(static_res['issues'])} potential issues found:\n{issue_text}"
        else:
            text = "✅ No cppcheck issues found."
        fb["sections"].append({
            "section": "Static Analysis",
            "score": round(static_res.get("score", 0) * 100, 1),
            "text": text
        })

    # --- Test Execution ---
    if test_res:
        if test_res.get("timed_out"):
            text = "❌ Program timed out — possibly waiting for input."
        elif not test_res.get("success"):
            text = f"⚠️ Program ran with errors:\n{test_res.get('stderr', '')}"
        else:
            text = f"✅ Program executed correctly.\nOutput: {test_res.get('stdout', '')}"
        fb["sections"].append({
            "section": "Execution Test",
            "score": round(test_res.get("score", 0) * 100, 1),
            "text": text
        })

    # --- Performance ---
    if perf_res:
        fb["sections"].append({
            "section": "Performance",
            "score": round(perf_res.get("score", 0) * 100, 1),
            "text": f"⏱️ Average runtime: {perf_res.get('avg_time', 0):.4f}s"
        })

    # --- Final Verdict ---
    final_score = fb["final_score"]
    if final_score >= 80:
        conclusion = "🏆 Excellent work! All checks passed."
    elif final_score >= 50:
        conclusion = "⚙️ Some improvements needed (style or efficiency)."
    else:
        conclusion = "❌ Major issues — check compilation or logic."

    fb["conclusion"] = conclusion
    return fb


# ====== Graph Builder ======
def build_grader_graph():
    """Create the LangGraph workflow."""
    g = StateGraph(GraderState)

    g.add_node("compile", compile_agent)
    g.add_node("static", static_agent)
    g.add_node("test", test_agent)
    g.add_node("perf", performance_agent)
    g.add_node("orchestrate", orchestrate)

    g.set_entry_point("compile")

    def after_compile(state: GraderState):
        if state.get("compile", {}).get("success"):
            return "run_checks"
        else:
            return "end"

    g.add_conditional_edges(
        "compile",
        after_compile,
        {"run_checks": "static", "end": "orchestrate"}
    )

    g.add_edge("static", "test")
    g.add_edge("test", "perf")
    g.add_edge("perf", "orchestrate")
    g.add_edge("orchestrate", END)

    return g.compile()
