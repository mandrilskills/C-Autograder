import subprocess
import time
from pathlib import Path
from typing import TypedDict, Dict, Any, List
from langgraph.graph import StateGraph, END
import asyncio
import os
import shutil

# === Utility: wrap async → sync for LangGraph ===
def make_sync(agent):
    def wrapper(state, config):
        result = agent(state, config)
        if asyncio.iscoroutine(result):
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    return loop.run_until_complete(result)
            except RuntimeError:
                pass
            return asyncio.run(result)
        else:
            return result
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

    # Use run_subprocess for asynchronous execution
    proc = await run_subprocess(cmd, cwd=str(run_dir), timeout=10) 

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
    # Only run static analysis if compilation succeeded
    if not state.get("compile", {}).get("success"):
        return {"static": {"success": False, "score": 0.0, "issues": ["Skipped static analysis due to compilation failure."]}}

    run_dir = Path(state["compile"]["run_dir"])
    issues = []
    try:
        # NOTE: cppcheck command must be available in the execution environment
        cpp = await run_subprocess(
            ["cppcheck", "--enable=warning,style,performance", "main.c"],
            timeout=15,
            cwd=str(run_dir)
        )
        out = cpp.stdout + cpp.stderr
        for line in out.splitlines():
            if line.strip():
                issues.append(line.strip())
    except Exception as e:
        issues.append(f"Cppcheck execution failed: {e}")
        pass
        
    score = max(0.0, 1.0 - 0.1 * len(issues))
    return {"static": {"success": True, "score": score, "issues": issues}}

async def test_agent(state: GraderState, config: Dict[str, Any]):
    # Only run tests if compilation succeeded
    if not state.get("compile", {}).get("success"):
        return {"test": {"success": False, "score": 0, "results": [], "passed": 0, "total": 0}}
        
    configurable = config.get("configurable", {})
    # Expects tests as [{"input": "...", "output": "..."}, ...]
    tests = configurable.get("tests", []) 
    run_dir = Path(state["compile"]["run_dir"])

    exe_path = Path(run_dir) / state["compile"]["exe_name"]
    if not exe_path.exists():
        return {"test": {"success": False, "score": 0, "results": []}}

    # Command to run the executable
    exec_cmd = [str(exe_path)] if os.name == "nt" else ["./" + exe_path.name]

    results = []
    passed = 0
    for t in tests:
        # Use run_subprocess for asynchronous execution
        proc = await run_subprocess(exec_cmd, input_data=t["input"], cwd=str(run_dir), timeout=5) 
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
    # Only run performance if compilation succeeded
    if not state.get("compile", {}).get("success"):
        return {"perf": {"success": False, "score": 0, "avg_time": 0}}
        
    run_dir = Path(state["compile"]["run_dir"])
    exe_path = Path(run_dir) / state["compile"]["exe_name"]

    if not exe_path.exists():
        return {"perf": {"success": False, "score": 0, "avg_time": 0}}

    exec_cmd = [str(exe_path)] if os.name == "nt" else ["./" + exe_path.name]

    sample_input = "2 3" # Using a generic small input for timing
    times = []
    
    # Run the program multiple times to get an average
    for _ in range(3):
        start = time.perf_counter()
        # Use run_subprocess for asynchronous execution
        await run_subprocess(exec_cmd, input_data=sample_input, cwd=str(run_dir), timeout=5) 
        times.append(time.perf_counter() - start)

    avg = sum(times) / len(times) if times else 0
    # Simple scoring logic based on average runtime
    score = 1.0 if avg < 0.05 else (0.7 if avg < 0.2 else 0.4)
    return {"perf": {"success": True, "score": score, "avg_time": avg}}

def orchestrate(state: GraderState, config: Dict[str, Any]):
    weights = {"compile": 0.25, "test": 0.45, "static": 0.15, "perf": 0.15}
    total = 0
    for k, w in weights.items():
        # Safely get the score, defaulting to 0 if the agent was skipped or failed
        total += w * state.get(k, {}).get("score", 0) 
    return {"final": {"score": total}}

def feedback(result: GraderState):
    compile_res = result.get("compile", {})
    test_res = result.get("test", {})
    static_res = result.get("static", {})
    perf_res = result.get("perf", {})
    final_res = result.get("final", {})

    fb = {"final_score": round(final_res.get("score", 0) * 100, 2), "sections": []}

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

def build_grader_graph():
    g = StateGraph(GraderState)
    # RENAME: Renamed 'compile' node to 'run_compile' to avoid conflict with the 'compile' state key.
    g.add_node("run_compile", make_sync(compile_agent))
    g.add_node("static", make_sync(static_agent))
    g.add_node("test", make_sync(test_agent))
    g.add_node("perf", make_sync(performance_agent))
    g.add_node("orchestrate", make_sync(orchestrate))

    # Updated entry point and edges to use the new node name
    g.set_entry_point("run_compile")
    g.add_edge("run_compile", "static")
    g.add_edge("static", "test")
    g.add_edge("test", "perf")
    g.add_edge("perf", "orchestrate")
    g.add_edge("orchestrate", END)
    return g.compile()

# --- Wrapper Function for Streamlit ---
def run_grader_pipeline(source_code: str, tests: List[Dict[str, str]]) -> Dict:
    """
    Builds and runs the C code grading graph, managing configuration and cleanup.
    
    Returns:
        The structured feedback dictionary from the feedback agent.
    """
    graph = build_grader_graph()
    submission_id = str(time.time()).replace(".", "") # Unique ID for run folder

    config = {
        "configurable": {
            "submission_id": submission_id,
            "source_code": source_code,
            "tests": tests
        }
    }
    
    run_dir = WORK_DIR / submission_id
    run_dir.mkdir(exist_ok=True)
    
    try:
        # Run the graph synchronously
        final_state = graph.invoke({}, config=config)
        
        # Return the structured feedback dictionary
        return feedback(final_state)
    
    except Exception as e:
        return {"final_score": 0.0, "sections": [{"section": "Pipeline Error", "score": 0, "text": f"Grader pipeline failed to execute: {e}"}], "conclusion": "❌ Grader failed due to a system error."}
    
    finally:
        # Crucial: Clean up the run directory containing the source/executable files
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)

# The summarize_with_llm function is not used by app.py's new logic, 
# but kept here if other parts of the LangGraph implementation needed it.
# def summarize_with_llm(result: GraderState):
#     try:
#         from llm_agents import generate_detailed_report
#         return generate_detailed_report(result)
#     except Exception:
#         return "LLM summary unavailable."
