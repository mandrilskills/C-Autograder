# llm_agents.py
import os
import logging
import google.generativeai as genai
from groq_llm import generate_test_cases_with_groq

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------- GEMINI SETUP ----------------
def configure_gemini():
    api_key = os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError("Gemini API key not found.")
    genai.configure(api_key=api_key)


def _call_gemini(prompt: str, max_output_tokens=900) -> str:
    """Internal Gemini 2.5 Flash call."""
    try:
        configure_gemini()
        model = genai.GenerativeModel("gemini-2.5-flash")
        # safer list format for compatibility
        response = model.generate_content([prompt],
            generation_config={"max_output_tokens": max_output_tokens})
        if hasattr(response, "text") and response.text:
            return response.text.strip()
        # capture blocked or empty cases
        meta = getattr(response, "prompt_feedback", "No feedback metadata.")
        logger.warning(f"Gemini returned no text. Metadata: {meta}")
    except Exception as e:
        logger.warning(f"Gemini 2.5 Flash failed: {e}")
    return None


# ---------------- TEST CASE GENERATION (Groq OSS 20B) ----------------
def generate_test_cases_with_logging(code_text: str, max_cases: int = 8) -> dict:
    """Uses Groq API (model: openai/gpt-oss-20b) for test case generation."""
    for attempt in range(2):
        res = generate_test_cases_with_groq(code_text, max_cases)
        if res["status"] == "ok" and res["tests"]:
            logger.info(f"Groq OSS 20B succeeded on attempt {attempt+1}")
            return res
        logger.warning(f"Groq OSS 20B attempt {attempt+1} failed: {res['reason']}")
    return {
        "status": "fallback",
        "tests": _heuristic_test_gen(code_text, max_cases),
        "reason": "Groq OSS 20B failed twice; heuristic fallback used",
    }


# ---------------- HEURISTIC FALLBACK ----------------
def _heuristic_test_gen(code_text: str, max_cases: int = 5):
    code = code_text.lower()
    if "largest" in code:
        return [
            "2 3 1::3.00 is the largest number.",
            "5 8 7::8.00 is the largest number.",
            "10 2 3::10.00 is the largest number.",
            "-5 -2 -10::-2.00 is the largest number.",
        ]
    elif "sum" in code:
        return ["1 2::3", "10 5::15", "-1 1::0"]
    elif "factorial" in code:
        return ["3::6", "5::120", "0::1"]
    else:
        return ["1::1", "2::2"]


# ---------------- GEMINI REPORT GENERATION ----------------
def generate_llm_report(evaluation: dict) -> str:
    """Generate detailed evaluation report using Gemini 2.5 Flash."""
    prompt = f"""
You are an expert C programming evaluator.

Analyze the following evaluation JSON and write a structured report with:
1. Summary
2. Compilation Details
3. Static Analysis
4. Functional Testing
5. Performance Evaluation
6. Recommendations

Evaluation JSON:
{evaluation}
"""
    report = _call_gemini(prompt)
    return report or "(LLM report generation failed — Gemini 2.5 Flash returned empty.)"


def test_gemini_connection() -> str:
    """Quick diagnostic for Gemini 2.5 Flash."""
    try:
        configure_gemini()
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(["Say 'Gemini 2.5 Flash connection successful.'"])
        if hasattr(response, "text") and response.text:
            return f"Gemini 2.5 Flash Response: {response.text.strip()}"
        return f"Gemini reachable but empty. Metadata: {getattr(response, 'prompt_feedback', 'No feedback')}"
    except Exception as e:
        return f"Gemini 2.5 Flash connection failed: {e}"
