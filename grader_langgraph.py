import subprocess
import time
from pathlib import Path
from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph, END
import asyncio
import os


# === Utility: wrap async → sync for LangGraph ===
def make_sync(agent):
    """Wrap async agent in sync for compatibility (works with Streamlit Cloud and Windows)."""
    def wrapper(state, config):
        return asyncio.run(agent(state, config))
    return wrapper


# === Setup ===
WORK_DIR = Path("runs")
WORK_DIR.mkdir(exist_ok=True)


# === Define State Schema ===
class GraderState(TypedDict, total=False):
    compile: dict
    static: dict
    test: dict
    perf: dict
    final: dict


# === Cross-platform subprocess helper ===
async def run_subprocess(cmd, input_data=None, timeout=None, cwd=None):
    """Runs subprocess safely with support for Windows and Linux."""
    loop = asyncio.get_event_loop()

    def _run():
        return subprocess.run(
            cmd,
            input=input_data if input_data else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True,
            cwd=cwd
        )

    return await loop.run_in_executor(None, _run)


# === Agents ===
async def compile_agent(state: GraderState, config: Dict[str, Any]):
    configurable = config.get("configurable", {})
    submission_id = configurable.get("submission_id", "default-id")
    source_code = configurable.get("source_code", "")

    run_dir = WORK_DIR / submission_id
    run_dir.mkdir(exist_ok=True)
    src = run_dir / "main.c"
    src.write_text(source_code)

    exe_name = "a.out.exe" if os.name == "nt" else "a.out"
    cmd = ["gcc", "-std=c11", "main.c", "-o", exe_name, "-Wall", "-Wextra"]

    proc = await run_subprocess(cmd, cwd=str(run_dir))

    success = proc.returncode == 0
    return {
        "compile": {
            "success": success,
            "stderr": proc.stderr,
            "stdout": proc.stdout,
            "run_dir": str(run_dir),
            "exe_name": exe_name,
            "score": 1.0 if success else 0.0
        }
    }


async def static_agent(state: GraderState, config: Dict[str, Any]):
    run_dir = Path(state["compile"]["run_dir"])
    issues = []
    try:
        cpp = subprocess.run(
            ["cppcheck", "--enable=warning,style,performance", "main.c"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            cwd=str(run_dir)
        )
        out = cpp.stdout + cpp.stderr
        for line in out.splitlines():
            if line.strip():
                issues.append(line.strip())
    except Exception:
        pass
    score = max(0.0, 1.0 - 0.1 * len(issues))
    return {"static": {"success": True, "score": score, "issues": issues}}


async def test_agent(state: GraderState, config: Dict[str, Any]):
    configurable = config.get("configurable", {})
    tests = configurable.get("tests", [])
    run_dir = Path(state["compile"]["run_dir"])

    exe_path = Path(run_dir) / state["compile"]["exe_name"]
    if not exe_path.exists():
        return {"test": {"success": False, "score": 0, "results": []}}

    # ✅ Cross-platform execution command
    exec_cmd = [str(exe_path)] if os.name == "nt" else ["./" + exe_path.name]

    results = []
    passed = 0
    for t in tests:
        proc = await run_subprocess(exec_cmd, input_data=t["input"], cwd=str(run_dir))
        out = proc.stdout.strip()
        ok = out == t["output"].strip()
        results.append({
            "input": t["input"],
            "expected": t["output"],
            "output": out,
            "passed": ok
        })
        if ok:
            passed += 1

    score = passed / len(tests) if tests else 0
    return {
        "test": {"success": True, "score": score, "results": results, "passed": passed, "total": len(tests)}
    }


async def performance_agent(state: GraderState, config: Dict[str, Any]):
    run_dir = Path(state["compile"]["run_dir"])
    exe_path = Path(run_dir) / state["compile"]["exe_name"]

    if not exe_path.exists():
        return {"perf": {"success": False, "score": 0, "avg_time": 0}}

    exec_cmd = [str(exe_path)] if os.name == "nt" else ["./" + exe_path.name]

    sample_input = "2 3"
    times = []
    for _ in range(3):
        start = time.perf_counter()
        await run_subprocess(exec_cmd, input_data=sample_input, cwd=str(run_dir))
        times.append(time.perf_counter() - start)

    avg = sum(times) / len(times)
    score = 1.0 if avg < 0.05 else (0.7 if avg < 0.2 else 0.4)
    return {"perf": {"success": True, "score": score, "avg_time": avg}}


def orchestrate(state: GraderState, config: Dict[str, Any]):
    weights = {"compile": 0.25, "test": 0.45, "static": 0.15, "perf": 0.15}
    total = 0
    for k, w in weights.items():
        total += w * state.get(k, {}).get("score", 0)
    return {"final": {"score": total}}


# === Feedback ===
def feedback(result: GraderState):
    compile_res = result.get("compile", {})
    test_res = result.get("test", {})
    static_res = result.get("static", {})
    perf_res = result.get("perf", {})
    final_res = result.get("final", {})

    fb = {"final_score": round(final_res.get("score", 0) * 100, 2), "sections": []}

    # Compilation
    fb["sections"].append({
        "section": "Compilation",
        "score": round(compile_res.get("score", 0) * 100, 1),
        "text": "✅ Compiled successfully." if compile_res.get("success")
        else f"❌ Compilation failed:\n\n{compile_res.get('stderr', 'Unknown error')}"
    })

    if compile_res.get("success"):
        if test_res:
            test_text = "\n".join(
                [f"Input: {r['input']} | Expected: {r['expected']} | Got: {r['output']} | {'✅' if r['passed'] else '❌'}"
                 for r in test_res.get("results", [])]
            )
            fb["sections"].append({
                "section": "Test Cases",
                "score": round(test_res.get("score", 0) * 100, 1),
                "text": test_text if test_text else "No test cases run."
            })

        if static_res:
            if static_res.get("issues"):
                fb["sections"].append({
                    "section": "Static Analysis",
                    "score": round(static_res.get("score", 0) * 100, 1),
                    "text": "\n".join(static_res.get("issues", []))
                })
            else:
                fb["sections"].append({
                    "section": "Static Analysis",
                    "score": 100,
                    "text": "✅ No issues found."
                })

        if perf_res:
            fb["sections"].append({
                "section": "Performance",
                "score": round(perf_res.get("score", 0) * 100, 1),
                "text": f"Avg runtime: {perf_res.get('avg_time', 0):.4f}s"
            })

    fb["conclusion"] = (
        "✅ Excellent work! All checks passed with high performance."
        if fb["final_score"] > 80
        else ("⚠️ Needs improvement — check logic or performance."
              if compile_res.get("success") else "❌ Compilation failed. Please fix errors and resubmit.")
    )

    return fb


# === Build LangGraph ===
def build_grader_graph():
    g = StateGraph(GraderState)
    g.add_node("compile", make_sync(compile_agent))
    g.add_node("static", make_sync(static_agent))
    g.add_node("test", make_sync(test_agent))
    g.add_node("perf", make_sync(performance_agent))
    g.add_node("orchestrate", make_sync(orchestrate))

    g.set_entry_point("compile")
    g.add_edge("compile", "static")
    g.add_edge("static", "test")
    g.add_edge("test", "perf")
    g.add_edge("perf", "orchestrate")
    g.add_edge("orchestrate", END)
    return g.compile()
