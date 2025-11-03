# llm_agents.py
import os
import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# -------------------------------------------------------------------
# Try to import Gemini SDK
# -------------------------------------------------------------------
try:
    import google.generativeai as genai
    GENAI_SDK = True
except Exception:
    GENAI_SDK = False
    logger.warning("google-generativeai not installed or unavailable.")

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

            # Extract response text robustly
            if hasattr(response, "text") and response.text:
                return response.text.strip()
            if hasattr(response, "candidates") and response.candidates:
                try:
                    return response.candidates[0].content.parts[0].text.strip()
                except Exception:
                    pass

            logger.warning(f"Gemini {m} returned no text field: {str(response)[:200]}")
        except Exception as e:
            logger.warning(f"Gemini model {m} failed: {e}")
            last_error = e
            continue

    logger.error(f"All Gemini models failed. Last error: {last_error}")
    return None

# -------------------------------------------------------------------
# Deterministic Test-Case Generator
# -------------------------------------------------------------------
def generate_test_cases_with_logging(code_text: str, max_cases: int = 8) -> Dict[str, Any]:
    """
    Generate test cases for a C program using Gemini or heuristic fallback.
    Returns {'status': 'ok'/'fallback', 'tests': [...], 'reason': '...'}
    """
    prompt = f"""
You are an automated C test case generator.

Given the following C program, generate {max_cases} realistic input/output pairs.
Each pair must be on a separate line using this format:

<input_values>::<expected_output>

Rules:
- Do NOT include any explanations, headings, or comments.
- Use realistic numeric inputs based on scanf format specifiers in the program.
- The expected output must exactly match what printf would print.
- Do not wrap the response in JSON or markdown.
- Avoid quotes or code blocks.

C program:
{code_text}
"""

    res_text = _call_gemini(prompt, max_output_tokens=400)

    # Try parsing Gemini output
    if res_text:
        lines = [ln.strip() for ln in res_text.splitlines() if ln.strip()]
        # Filter out possible markdown/code block markers
        lines = [ln for ln in lines if not ln.startswith("```") and "::" in ln]
        if lines:
            logger.info(f"Gemini generated {len(lines)} test cases successfully.")
            return {"status": "ok", "tests": lines[:max_cases], "reason": "Gemini test-case generation succeeded."}

    # If Gemini failed or returned junk → fallback deterministic generator
    fallback_tests = _heuristic_test_gen(code_text, max_cases)
    logger.warning("Gemini test-case generation failed. Using fallback heuristic.")
    return {"status": "fallback", "tests": fallback_tests, "reason": "Gemini not available or returned none; used heuristic fallback"}

# -------------------------------------------------------------------
# Simple Fallback Heuristic
# -------------------------------------------------------------------
def _heuristic_test_gen(code_text: str, max_cases: int = 6) -> List[str]:
    code = code_text.lower()
    out = []
    if "scanf" in code and "printf" in code and "+" in code:
        out = ["2 3::5", "10 20::30", "-1 1::0", "0 0::0"]
    elif "largest" in code and "if" in code:
        out = [
            "2 3 1::3.00 is the largest number.",
            "5 8 7::8.00 is the largest number.",
            "10 2 3::10.00 is the largest number.",
            "-5 -2 -10::-2.00 is the largest number."
        ]
    elif "factorial" in code:
        out = ["3::6", "5::120", "0::1"]
    elif "reverse" in code:
        out = ["123::321", "100::1"]
    elif "prime" in code:
        out = ["2::prime", "4::not prime", "17::prime"]
    else:
        out = ["1::1", "2::2", "3::3"]
    return out[:max_cases]

# -------------------------------------------------------------------
# LLM Report Generator
# -------------------------------------------------------------------
def generate_detailed_report(evaluation: Dict[str, Any]) -> str:
    """
    Generate a structured evaluation report using Gemini, or fallback if unavailable.
    """
    prompt = (
        "You are an expert C instructor. Based on the evaluation JSON below, write a structured report with these sections:\n"
        "Summary, Compilation, Static Analysis, Functional Tests, Performance, and Recommendations.\n"
        "Do NOT change numeric values or results. Keep tone analytical and professional.\n\n"
        "Evaluation JSON:\n" + json.dumps(evaluation, indent=2)
    )

    res = _call_gemini(prompt, max_output_tokens=900)
    if res:
        return res

    # Fallback text report
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
    lines.append("Recommendations: Address static warnings, verify I/O format, and optimize logic as needed.")
    return "\n".join(lines)
