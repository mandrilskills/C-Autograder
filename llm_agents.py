# llm_agents.py
import os
import logging
import google.generativeai as genai
from groq_llm import generate_test_cases_with_groq

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --------------- Gemini Setup ---------------
def configure_gemini():
    api_key = os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError("Gemini API key not found in environment variables.")
    genai.configure(api_key=api_key)

def _call_gemini(prompt: str, model_name: str = "gemini-2.5-flash", max_output_tokens: int = 800) -> str:
    try:
        configure_gemini()
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt, generation_config={"max_output_tokens": max_output_tokens})
        if hasattr(response, "text") and response.text:
            return response.text.strip()
    except Exception as e:
        logger.warning(f"Gemini model {model_name} failed: {e}")
    return None

# --------------- Test-Case Generation (via Groq) ---------------
def generate_test_cases_with_logging(code_text: str, max_cases: int = 8) -> dict:
    res = generate_test_cases_with_groq(code_text, max_cases)
    if res["status"] == "ok" and res["tests"]:
        return res

    logger.warning("Groq test generation failed, using fallback heuristic.")
    return {
        "status": "fallback",
        "tests": _heuristic_test_gen(code_text, max_cases),
        "reason": "Groq unavailable; used heuristic fallback"
    }

def _heuristic_test_gen(code_text: str, max_cases: int = 5):
    code = code_text.lower()
    if "largest" in code:
        return [
            "2 3 1::3.00 is the largest number.",
            "5 8 7::8.00 is the largest number.",
            "10 2 3::10.00 is the largest number.",
            "-5 -2 -10::-2.00 is the largest number."
        ]
    elif "sum" in code:
        return ["1 2::3", "10 5::15", "-1 1::0"]
    elif "factorial" in code:
        return ["3::6", "5::120", "0::1"]
    else:
        return ["1::1", "2::2"]

# --------------- Gemini Report Generation ---------------
def generate_llm_report(evaluation: dict) -> str:
    prompt = f"""
You are an expert C programming evaluator.

Based on the following evaluation JSON, write a detailed analytical report with:
1. A Summary
2. Compilation analysis
3. Static Analysis summary
4. Functional Test insights
5. Performance overview
6. Key Recommendations

Keep tone professional, structured, and readable.

Evaluation JSON:
{evaluation}
"""
    report = _call_gemini(prompt, model_name="gemini-2.5-flash")
    if not report:
        logger.info("Gemini 2.5 Flash failed, using 1.5 Pro fallback...")
        report = _call_gemini(prompt, model_name="gemini-1.5-pro")
    return report or "(LLM report generation failed — no output received.)"

# --------------- Connectivity Test ---------------
def test_gemini_connection() -> str:
    try:
        txt = _call_gemini("Say 'Gemini connection successful.'", model_name="gemini-2.5-flash", max_output_tokens=10)
        if txt:
            return f"Gemini Response: {txt}"
        configure_gemini()
        model = genai.GenerativeModel("gemini-1.5-pro")
        resp = model.generate_content("Say 'Gemini 1.5 Pro reachable.'")
        if hasattr(resp, "text") and resp.text:
            return f"Gemini Response (1.5 Pro): {resp.text.strip()}"
        return "Gemini reachable but no text returned."
    except Exception as e:
        return f"Gemini connection failed: {e}"
