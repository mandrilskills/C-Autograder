# llm_agents.py
import os
import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Try to import google generative ai SDK if present
try:
    import google.generativeai as genai
    GENAI_SDK = True
except Exception:
    GENAI_SDK = False

def _call_gemini(prompt: str, max_output_tokens: int = 800) -> Optional[str]:
    """
    Robust Gem API caller. Returns text or None with logged reason.
    """
    if not GENAI_SDK:
        logger.warning("Google generative SDK not installed.")
        return None
    api_key = os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("GENAI_API_KEY not set.")
        return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt, generation_config={"max_output_tokens": max_output_tokens})
        # Try multiple response shapes
        if hasattr(response, "text") and response.text:
            return response.text.strip()
        if hasattr(response, "candidates") and response.candidates:
            cand = response.candidates[0]
            # candidate.content.parts[0].text is common
            try:
                return cand.content.parts[0].text.strip()
            except Exception:
                # try dict-like
                try:
                    return cand["content"]["parts"][0]["text"].strip()
                except Exception:
                    pass
        # last resort
        logger.warning("Gemini returned unexpected shape: %s", str(response)[:400])
        return None
    except Exception as e:
        logger.exception("Gemini call failed: %s", e)
        return None

def generate_test_cases_with_logging(code_text: str, max_cases:int=8) -> Dict[str,Any]:
    """
    Attempt to generate test cases with Gemini. Returns structure:
    {"status":"ok"/"fallback", "tests":[...], "reason": "..."}
    """
    prompt = (
        "Generate up to {max} practical deterministic test cases for the following C program. "
        "Return them in a compact format, one test per line. Acceptable formats: JSON list of dicts, or lines 'input::expected', "
        "or input-only lines. Do not add commentary.\n\nPROGRAM:\n".format(max=max_cases) + code_text
    )

    res_text = _call_gemini(prompt, max_output_tokens=400)
    if res_text:
        # parse lines; prefer JSON if returned
        # attempt JSON parse
        parsed = None
        try:
            parsed = json.loads(res_text)
        except Exception:
            parsed = None
        tests = []
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict) and ("input" in item or "expected" in item):
                    tests.append(json.dumps(item) if False else f"{item.get('input','')}::{item.get('expected','')}")
            if tests:
                return {"status":"ok","tests":tests,"reason":"parsed JSON list"}
        # fallback: split lines and keep those that are not empty
        lines = [ln.strip() for ln in res_text.splitlines() if ln.strip()]
        # if lines look like JSON objects, convert to input::expected
        out_lines=[]
        for ln in lines:
            ln_stripped = ln.strip()
            # single-line JSON object?
            try:
                obj = json.loads(ln_stripped)
                if isinstance(obj, dict):
                    inp = obj.get("input","")
                    exp = obj.get("expected","")
                    out_lines.append(f"{inp}::{exp}")
                    continue
            except Exception:
                pass
            out_lines.append(ln_stripped)
        if out_lines:
            return {"status":"ok","tests": out_lines[:max_cases], "reason":"parsed plain lines from Gemini"}
    # If we reach here, Gemini failed — fallback deterministic heuristic generator
    fallback_tests = _heuristic_test_gen(code_text, max_cases)
    return {"status":"fallback","tests": fallback_tests, "reason":"Gemini not available or returned none; used heuristic fallback"}

def _heuristic_test_gen(code_text: str, max_cases: int = 6) -> List[str]:
    """
    Simple deterministic fallback generator (no LLM). Looks for common patterns.
    """
    ct = code_text.lower()
    out=[]
    if "scanf" in ct and "printf" in ct and "+" in ct:
        out = ["2 3::5","10 20::30","-1 1::0","0 0::0"]
    elif "factorial" in ct:
        out = ["3::6","5::120","0::1"]
    elif "reverse" in ct:
        out = ["123::321","100::1"]
    elif "prime" in ct:
        out = ["2::prime","4::not prime","17::prime"]
    else:
        # generic echo tests (useful for trivial programs)
        out = ["input1::input1", "hello::hello", "42::42"]
    return out[:max_cases]

def generate_detailed_report(evaluation: Dict[str, Any]) -> str:
    """
    Build a clear prompt and call Gemini. If Gemini fails, produce a structured fallback report.
    """
    prompt = (
        "You are an experienced C instructor. Using ONLY the JSON below, write a structured report: "
        "Summary, Compilation, Static Analysis, Functional Tests, Performance, Recommendations. "
        "Do NOT change numeric scores. JSON:\n" + json.dumps(evaluation, indent=2)
    )
    res = _call_gemini(prompt, max_output_tokens=900)
    if res:
        return res
    # fallback text
    lines = []
    lines.append("FALLBACK REPORT — LLM not available")
    lines.append(f"Final Score: {evaluation.get('final_score', 'N/A')}")
    comp = evaluation.get("compile", {})
    if comp.get("status")!="success":
        lines.append("Compilation failed. Stderr:")
        lines.append(comp.get("stderr",""))
    else:
        lines.append("Compiled successfully.")
    static = evaluation.get("static",{})
    lines.append(f"Static analysis issues: {len(static.get('issues',[]))}")
    for it in static.get("issues",[])[:10]:
        lines.append("- " + str(it))
    test = evaluation.get("test",{})
    lines.append(f"Tests passed: {test.get('passed',0)} / {test.get('total',0)}")
    for r in test.get("results",[])[:10]:
        lines.append(f"Input: {r.get('input')} -> actual: {r.get('actual')} success: {r.get('success')} comment: {r.get('comment')}")
    lines.append("Recommendations: fix compile errors, address cppcheck warnings, add/adjust tests to match input format, handle timeouts.")
    return "\n".join(lines)
