import asyncio
import subprocess
import time
import uuid
from pathlib import Path
from typing import TypedDict, Dict, Any, Optional
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

# ====== Safe subprocess helper (supports cwd) ======
async def run_subprocess(cmd, input_data: Optional[str] = None, timeout: Optional[int] = 3, cwd: Optional[str] = None):
    """Run a subprocess asynchronously with optional stdin input and timeout."""
    loop = asyncio.get_event_loop()

    def _run():
        try:
            return subprocess.run(
                cmd,
                input=input_data if input_data is not None else "",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(cmd, 1, "", "❌ Program timed out (possibly waiting for input)")

    return await loop.run_in_executor(None, _run)

# ====== Agents (all accept config=None) ======
async def compile_agent(state: GraderState, config: Dict[str, Any] = None):
    """Compile the uploaded C source file with full path awareness."""
    configurable = (config or {}).get("configurable", {})
    submission_id = configurable.get("submission_id", f"run_{uuid.uuid4().hex[:6]}")
    source_code = configurable.get("source_code", "")

    # Create unique subfolder
    run_dir = WORK_DIR / f"{submission_id}_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(exist_ok=True)

    src = run_dir / "main.c"
    src.write_text(source_code)
    exe = run_dir / "a.out"

    # Safety check
    if not src.exists():
        return {
            "compile": {
                "success": False,
                "stderr": "❌ Source file not found.",
                "stdout": "",
                "run_dir": str(run_dir),
                "exe": str(exe),
                "score": 0.0,
            }
        }

    # ✅ Use full absolute path instead of cwd-relative name
    cmd = ["gcc", "-std=c11", str(src), "-o", str(exe), "-Wall", "-Wextra"]
    proc = await run_subprocess(cmd, timeout=10)  # remove cwd argument

    success = proc.returncode == 0
    stderr_text = proc.stderr.strip()

    # Friendly message for missing main
    if "undefined reference to `main'" in stderr_text or "undefined reference to `main`" in stderr_text:
        stderr_text = (
            "❌ Linker error: no `main()` found.\n"
            "This can occur if the compiler didn't read your file correctly. "
            "Please ensure the uploaded file isn't empty or malformed."
        )

    return {
        "compile": {
            "success": success,
            "stderr": stderr_text,
            "stdout": proc.stdout,
            "run_dir": str(run_dir),
            "exe": str(exe),
            "score": 1.0 if success else 0.0,
        }
    }


async def static_agent(state: GraderState, config: Dict[str, Any] = None):
    """Run cppcheck static analysis."""
    # If compile not present or failed, return skipped
    if not state.get("compile", {}).get("success"):
        return {"static": {"success": False, "score": 0.0, "issues": ["Skipped due to compile failure."]}}

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

async def performance_agent(state: GraderState, config: Dict[str, Any] = None):
    """Measure runtime for a short sample input (prevents hangs with timeout)."""
    if not state.get("compile", {}).get("success"):
        return {"perf": {"success": False, "score": 0.0, "avg_time": 0.0}}

    run_dir = Path(state["compile"]["run_dir"])
    exe_path = run_dir / "a.out"
    if not exe_path.exists():
        return {"perf": {"success": False, "score": 0.0, "avg_time": 0.0}}

    sample_input = "0 0\n"
    times = []
    for _ in range(3):
        start = time.perf_counter()
        proc = await run_subprocess(["./a.out"], input_data=sample_input, timeout=3, cwd=str(run_dir))
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    avg = sum(times) / len(times) if times else 0.0
    score = 1.0 if avg < 0.1 else (0.7 if avg < 1.0 else 0.3)
    return {"perf": {"success": True, "score": score, "avg_time": avg}}

def orchestrate(state: GraderState, config: Dict[str, Any] = None):
    """Combine results into final weighted score."""
    weights = {"compile": 0.5, "static": 0.25, "perf": 0.25}
    if not state.get("compile", {}).get("success", False):
        return {"final": {"score": 0.0}}
    total = 0.0
    for k, w in weights.items():
        total += w * state.get(k, {}).get("score", 0.0)
    return {"final": {"score": total}}

# ====== Feedback formatter ======
def feedback(result: GraderState):
    compile_res = result.get("compile", {})
    static_res = result.get("static", {})
    perf_res = result.get("perf", {})
    final_res = result.get("final", {})

    fb = {"final_score": round(final_res.get("score", 0.0) * 100, 2), "sections": []}

    # Compilation
    fb["sections"].append({
        "section": "Compilation",
        "score": round(compile_res.get("score", 0.0) * 100, 1),
        "text": "✅ Compiled successfully." if compile_res.get("success") else f"❌ Compilation failed:\n\n{compile_res.get('stderr', '').strip()}"
    })

    # Static
    if static_res:
        issues = static_res.get("issues", [])
        if not issues:
            text = "✅ No issues found."
        else:
            text = "⚠️ Static analysis reported issues:\n" + "\n".join(f"- {i}" for i in issues[:10])
            if len(issues) > 10:
                text += f"\n... and {len(issues)-10} more."
        fb["sections"].append({
            "section": "Static Analysis",
            "score": round(static_res.get("score", 0.0) * 100, 1),
            "text": text
        })
    else:
        fb["sections"].append({
            "section": "Static Analysis",
            "score": 0.0,
            "text": "⚠️ Static analysis skipped or unavailable."
        })

    # Performance
    if perf_res:
        fb["sections"].append({
            "section": "Performance",
            "score": round(perf_res.get("score", 0.0) * 100, 1),
            "text": f"⏱️ Avg runtime: {perf_res.get('avg_time', 0.0):.4f}s"
        })

    # Conclusion
    fb["conclusion"] = (
        "🏆 Excellent! Good code and performance."
        if fb["final_score"] >= 80 else
        ("⚙️ Some improvements needed." if fb["final_score"] >= 50 else "❌ Major issues — fix compilation or logic.")
    )
    return fb

# ====== Graph builder ======
def build_grader_graph():
    g = StateGraph(GraderState)

    g.add_node("compile", compile_agent)
    g.add_node("static", static_agent)
    g.add_node("perf", performance_agent)
    g.add_node("orchestrate", orchestrate)

    g.set_entry_point("compile")

    def after_compile(state: GraderState):
        if state.get("compile", {}).get("success"):
            return "next"
        return "end"

    g.add_conditional_edges("compile", after_compile, {"next": "static", "end": "orchestrate"})
    g.add_edge("static", "perf")
    g.add_edge("perf", "orchestrate")
    g.add_edge("orchestrate", END)

    return g.compile()

