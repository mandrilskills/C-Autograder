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
        raise EnvironmentError("Gemini API key not found in environment variables.")
    genai.configure(api_key=api_key)


def _call_gemini(prompt: str, model_name="gemini-2.5-flash", max_output_tokens=900) -> str:
    """Internal Gemini call"""
    try:
        configure_gemini()
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            prompt, generation_config={"max_output_tokens": max_output_tokens}
        )
        if hasattr(response, "text") and response.text:
            return response.text.strip()
    except Exception as e:
        logger.warning(f"Gemini model {model_name} failed: {e}")
    return None


# ---------------- TEST CASE GENERATION (Groq + OSS 20B) ----------------
def generate_test_cases_with_logging(code_text: str, max_cases: int = 8) -> dict:
    """Uses Groq API (model: openai/gpt-oss-20b) for test case generation."""
    res = generate_test_cases_with_groq(code_text, max_cases)
    if res["status"] == "ok" and res["tests"]:
        return res
    logger.warning("Groq OSS 20B failed, using heuristic fallback.")
    return {
        "status": "fallback",
        "tests": _heuristic_test_gen(code_text, max_cases),
        "reason": "Groq OSS 20B unavailable; heuristic fallback used",
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
    """Generate detailed evaluation report using Gemini LLM."""
    prompt = f"""
You are an expert C programming evaluator.

Based on the following evaluation JSON, write a detailed structured report containing:
1. Summary
2. Compilation Details
3. Static Analysis
4. Functional Testing
5. Performance Evaluation
6. Recommendations

Ensure the response is analytical, technically sound, and formatted clearly.

Evaluation JSON:
{evaluation}
"""
    report = _call_gemini(prompt, model_name="gemini-2.5-flash")
    if not report:
        logger.info("Gemini 2.5 Flash failed, trying 1.5 Pro...")
        report = _call_gemini(prompt, model_name="gemini-1.5-pro")
    return report or "(LLM report generation failed.)"


def test_gemini_connection() -> str:
    try:
        txt = _call_gemini("Say 'Gemini connection successful.'", "gemini-2.5-flash", 10)
        if txt:
            return f"Gemini Response: {txt}"
        return "Gemini reachable but empty."
    except Exception as e:
        return f"Gemini connection failed: {e}"

