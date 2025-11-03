# llm_agents.py
import os
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# -------------------- Setup --------------------
def configure_gemini():
    api_key = os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError("Gemini API key not found in environment variables.")
    genai.configure(api_key=api_key)

def _call_gemini(prompt: str, model_name: str = "gemini-2.5-flash", max_output_tokens: int = 500) -> str:
    """
    Generic Gemini API call with safe fallback.
    """
    try:
        configure_gemini()
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt, generation_config={"max_output_tokens": max_output_tokens})
        if hasattr(response, "text") and response.text:
            return response.text.strip()
    except Exception as e:
        logger.warning(f"Gemini model {model_name} failed: {e}")
    return None

# -------------------- Heuristic Fallback --------------------
def _heuristic_test_gen(code_text: str, max_cases: int = 5):
    """
    Fallback test case generator when Gemini fails or is unavailable.
    """
    lines = []
    if "largest" in code_text.lower():
        lines = [
            "2 3 1::3.00 is the largest number.",
            "5 8 7::8.00 is the largest number.",
            "10 2 3::10.00 is the largest number.",
            "-5 -2 -10::-2.00 is the largest number.",
        ]
    elif "sum" in code_text.lower():
        lines = [
            "1 2::3",
            "5 7::12",
            "10 -2::8",
        ]
    else:
        lines = ["42::42", "0::0", "5::5"]
    return lines[:max_cases]

# -------------------- Test Case Generation --------------------
def generate_test_cases_with_logging(code_text: str, max_cases: int = 8) -> dict:
    """
    Generate test cases using Gemini 2.5 Flash, fallback to Gemini 1.5 Pro, then heuristic.
    """
    # Safer reworded prompt (avoids "simulate user input")
    prompt = f"""
You are a software quality assistant.

Review the following C program and suggest up to {max_cases} sample cases
that could verify its correctness.

List each case in one line using this format:
<example_values>::<expected_program_output>

Use realistic numeric examples when applicable.
Do NOT include explanations or code fences.

C program:
{code_text}
"""

    # ---- Try gemini-2.5-flash first ----
    res_text = _call_gemini(prompt, model_name="gemini-2.5-flash", max_output_tokens=400)

    # ---- Fallback to 1.5-pro if flash fails ----
    if not res_text:
        try:
            logger.info("Gemini 2.5 Flash returned None, trying 1.5 Pro...")
            configure_gemini()
            model = genai.GenerativeModel("gemini-1.5-pro")
            response = model.generate_content(prompt, generation_config={"max_output_tokens": 400})
            if hasattr(response, "text") and response.text:
                res_text = response.text.strip()
                logger.info("Gemini 1.5 Pro succeeded.")
        except Exception as e:
            logger.warning(f"Gemini 1.5 Pro test generation failed: {e}")

    # ---- Parse Gemini response ----
    if res_text:
        lines = [ln.strip() for ln in res_text.splitlines() if ln.strip()]
        lines = [ln for ln in lines if "::" in ln and not ln.startswith("```")]
        if lines:
            logger.info(f"Gemini produced {len(lines)} test cases.")
            return {"status": "ok", "tests": lines[:max_cases], "reason": "Gemini succeeded"}

    # ---- Heuristic fallback ----
    fallback_tests = _heuristic_test_gen(code_text, max_cases)
    logger.warning("Gemini returned None — using heuristic fallback.")
    return {"status": "fallback", "tests": fallback_tests, "reason": "Gemini not available or returned none; used heuristic fallback"}

# -------------------- LLM-based Report Generation --------------------
def generate_llm_report(evaluation: dict) -> str:
    """
    Generate a structured analysis report based on evaluation JSON.
    """
    prompt = f"""
You are an expert C programming evaluator.
Using the following structured evaluation JSON, write a detailed feedback report
for the student explaining the results clearly.

Guidelines:
- Start with a summary of overall performance.
- Include sections for Compilation, Static Analysis, Functional Tests, and Performance.
- Highlight strengths and weaknesses.
- Provide actionable improvement suggestions.
- Keep tone constructive and professional.

Evaluation JSON:
{evaluation}
"""

    report = _call_gemini(prompt, model_name="gemini-2.5-flash", max_output_tokens=800)
    if not report:
        logger.warning("Gemini 2.5 Flash failed to generate report, using 1.5 Pro fallback...")
        try:
            configure_gemini()
            model = genai.GenerativeModel("gemini-1.5-pro")
            resp = model.generate_content(prompt, generation_config={"max_output_tokens": 800})
            if hasattr(resp, "text") and resp.text:
                report = resp.text.strip()
        except Exception as e:
            logger.warning(f"Gemini 1.5 Pro report generation failed: {e}")

    return report or "(LLM report generation failed — no output received.)"

# -------------------- Diagnostics --------------------
def test_gemini_connection() -> str:
    """
    Verify Gemini connectivity for both models.
    """
    try:
        txt = _call_gemini("Say 'Gemini connection successful.'", model_name="gemini-2.5-flash", max_output_tokens=10)
        if txt:
            return f"Gemini Response: {txt}"
        logger.info("Gemini 2.5 Flash unavailable, testing 1.5 Pro...")
        configure_gemini()
        model = genai.GenerativeModel("gemini-1.5-pro")
        resp = model.generate_content("Say 'Gemini connection successful.'")
        if hasattr(resp, "text") and resp.text:
            return f"Gemini Response (1.5 Pro): {resp.text.strip()}"
        return "Gemini models reachable but no response text."
    except Exception as e:
        return f"Gemini connection failed: {e}"
