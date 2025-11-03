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
    logger.warning("google-generativeai not installed.")

# -------------------------------------------------------------------
# Robust Gemini Caller with Automatic Model Fallback
# -------------------------------------------------------------------
def _call_gemini(prompt: str, max_output_tokens: int = 800) -> Optional[str]:
    """
    Robust Gemini API call with automatic model fallback and debug logs.
    """
    if not GENAI_SDK:
        logger.warning("google-generativeai not installed.")
        return None

    api_key = os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("GENAI_API_KEY missing in environment.")
        return None

    genai.configure(api_key=api_key)
    model_names = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    last_error = None

    for m in model_names:
        try:
            logger.info(f"Attempting Gemini call with model: {m}")
            model = genai.GenerativeModel(m)
            response = model.generate_content(
                prompt, generation_config={"max_output_tokens": max_output_tokens}
            )

            # Extract response text robustly across SDK versions
            if hasattr(response, "text") and response.text:
                return response.text.strip()
            if hasattr(response, "candidates") and response.candidates:
                try:
                    return response.candidates[0].content.parts[0].text.strip()
                except Exception:
                    pass

            logger.warning(f"Gemini {m} returned no text field: {str(response)[:300]}")
        except Exception as e:
            logger.warning(f"Gemini model {m} failed: {e}")
            last_error = e
            continue

    logger.error(f"All Gemini models failed. Last error: {last_error}")
    return None

# -------------------------------------------------------------------
# Test Case Generator
# -------------------------------------------------------------------
def generate_test_cases_with_logging(code_text: str, max_cases: int = 8) -> Dict[str, Any]:
    """
    Attempt to generate test cases with Gemini or fallback heuristic.
    """
    prompt = (
        "Generate up to {max} practical deterministic test cases for the following C program. "
        "Return them in a compact format, one per line. Use either JSON list or 'input::expected' pairs.\n\nPROGRAM:\n"
    ).format(max=max_cases) + code_text

    res_text = _call_gemini(prompt, max_output_tokens=400)
    if res_text:
        try:
            parsed = json.loads(res_text)
            if isinstance(parsed, list):
                tests = []
                for item in parsed:
                    if isinstance(item, dict):
                        tests.append(f"{item.get('input','')}::{item.get('expected','')}")
                    else:
                        tests.append(str(item))
                return {"status": "ok", "tests": tests[:max_cases], "reason": "parsed JSON list"}
        except Exception:
            pass

        lines = [ln.strip() for ln in res_text.splitlines() if ln.strip()]
        if lines:
            return {"status": "ok", "tests": lines[:max_cases], "reason": "parsed plain lines from Gemini"}

    # Fallback if LLM fails
    fallback_tests = _heuristic_test_gen(code_text, max_cases)
    return {"status": "fallback", "tests": fallback_tests, "reason": "Gemini not available or returned none; used heuristic fallback"}

# -------------------------------------------------------------------
# Simple Fallback Heuristic
# -------------------------------------------------------------------
def _heuristic_test_gen(code_text: str, max_cases: int = 6) -> List[str]:
    code = code_text.lower()
    out = []
    if "scanf" in code and "printf" in code and "+" in code:
        out = ["2 3::5", "10 20::30", "-1 1::0", "0 0::0"]
    elif "factorial" in code:
        out = ["3::6", "5::120", "0::1"]
    elif "reverse" in code:
        out = ["123::321", "100::1"]
    elif "prime" in code:
        out = ["2::prime", "4::not prime", "17::prime"]
    else:
        out = ["input1::input1", "hello::hello", "42::42"]
    return out[:max_cases]

# -------------------------------------------------------------------
# LLM Report Generator
# -------------------------------------------------------------------
def generate_detailed_report(evaluation: Dict[str, Any]) -> str:
    prompt = (
        "You are an experienced C instructor. Using ONLY the JSON below, write a structured report: "
        "Summary, Compilation, Static Analysis, Functional Tests, Performance, Recommendations. "
        "Do NOT alter numeric scores.\n\nJSON:\n" + json.dumps(evaluation, indent=2)
    )

    res = _call_gemini(prompt, max_output_tokens=900)
    if res:
        return res

    # Fallback report
    lines = ["FALLBACK REPORT — LLM not available"]
    lines.append(f"Final Score: {evaluation.get('final_score', 'N/A')}")
    comp = evaluation.get("compile", {})
    if comp.get("status") != "success":
        lines.append("Compilation failed. Stderr:")
        lines.append(comp.get("stderr", ""))
    else:
        lines.append("Compiled successfully.")
    static = evaluation.get("static", {})
    lines.append(f"Static issues: {len(static.get('issues', []))}")
    for it in static.get("issues", [])[:5]:
        lines.append("- " + str(it))
    test = evaluation.get("test", {})
    lines.append(f"Tests passed: {test.get('passed', 0)} / {test.get('total', 0)}")
    lines.append("Recommendations: Fix compile errors, resolve cppcheck warnings, and recheck I/O format.")
    return "\n".join(lines)
