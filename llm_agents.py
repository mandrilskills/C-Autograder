"""
llm_agents.py
Manages LLM interactions for C Autograder.
Includes fallback logic for test case generation and detailed report writing.
"""

import os
import logging
from typing import Any, Dict, List, Optional

# Optional Gemini SDK import
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =====================
#  Helper: LLM Wrapper
# =====================

def call_gemini(prompt: str, timeout: int = 30, max_output_tokens: int = 512) -> Optional[str]:
    """Safely call Gemini model if available."""
    if not GENAI_AVAILABLE:
        logger.warning("Gemini SDK not installed. Returning None.")
        return None

    try:
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GENAI_API_KEY")
        if not api_key:
            logger.warning("Gemini API key not configured.")
            return None

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_output_tokens},
        )

        if response and hasattr(response, "text"):
            return response.text.strip()
        else:
            logger.error("Gemini returned no text part.")
            return None

    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
        return None


# =====================================
#  LLM-based or fallback test generator
# =====================================

def generate_test_cases(code_text: str, max_prompt_tokens: int = 1024) -> List[str]:
    """
    Generate test cases for the given C program.
    Uses LLM if available, else rule-based heuristics.
    """
    if not code_text.strip():
        return []

    # --- 1️⃣ Try LLM first ---
    prompt = (
        "Generate up to 5 simple input-output test cases for the following C program.\n"
        "Format each case as: <input>::<expected_output>\n"
        f"{code_text}\n"
    )
    text = call_gemini(prompt, timeout=30, max_output_tokens=512)
    if text:
        lines = [line.strip() for line in text.splitlines() if "::" in line]
        if lines:
            logger.info(f"LLM generated {len(lines)} test cases.")
            return lines

    # --- 2️⃣ Fallback rule-based generation ---
    logger.warning("LLM unavailable or failed. Using fallback test generator.")

    code_lower = code_text.lower()
    if "scanf" in code_lower and "printf" in code_lower and "+" in code_lower:
        return ["2 3::5", "10 15::25", "-5 5::0", "0 0::0"]

    if "factorial" in code_lower:
        return ["3::6", "5::120", "0::1"]

    if "average" in code_lower or "mean" in code_lower:
        return ["2 4::3", "10 20::15"]

    if "reverse" in code_lower:
        return ["123::321", "9870::789"]

    if "if" in code_lower and "<" in code_lower:
        return ["5::Positive", "-2::Negative", "0::Zero"]

    # generic fallback
    return ["1::1", "2::2"]


# ===================================
#  Human-readable grading report
# ===================================

def generate_detailed_report(context: Dict[str, Any]) -> str:
    """Generate justified human-readable report, even if LLM fails."""
    if not isinstance(context, dict):
        return "Invalid grading context."

    code = context.get("code", "<code omitted>")
    score = context.get("score", 0)
    compile_info = context.get("compile", {})
    static_info = context.get("static", {})
    test_info = context.get("test", {})
    perf_info = context.get("perf", {})

    # --- Try Gemini for rich report ---
    prompt = (
        "You are an expert C programming instructor. "
        "Write a detailed, human-readable evaluation of this student's code. "
        "Include sections: Compilation, Static Analysis, Functional Testing, Performance, Final Evaluation.\n\n"
        f"CODE:\n{code}\n\nCONTEXT:\n{context}\n"
    )

    text = call_gemini(prompt, timeout=45, max_output_tokens=1000)
    if text:
        return text

    # --- Fallback human text (no LLM) ---
    report = f"""
    C PROGRAMMING EVALUATION REPORT
    ---------------------------------------

    FINAL SCORE: {score}/100

    COMPILATION:
    {("✅ Successful compilation with no errors." if compile_info.get("status") == "success"
      else "❌ Compilation failed. Please check syntax and include headers properly.")}

    STATIC ANALYSIS:
    {("✅ No code issues detected." if not static_info.get("issues")
      else "⚠️ Issues found: " + ", ".join(static_info.get("issues", [])))}

    FUNCTIONAL TESTING:
    {("✅ All test cases passed."
      if test_info.get("passed", 0) == test_info.get("total", 0) and test_info.get("total", 0) > 0
      else "⚠️ Missing or failing test cases. Ensure correctness and edge case coverage.")}

    PERFORMANCE:
    {perf_info.get("comment", "Performance within acceptable range.")}

    OVERALL EVALUATION:
    The submitted code demonstrates understanding of syntax and structure. 
    To improve your score, focus on providing valid test cases and ensuring logic correctness.
    """

    return report.strip()
