# llm_agents.py
"""
LLM helpers for:
- generating candidate test cases (Gemini if available, fallback heuristics otherwise)
- generating the FINAL human-readable report based strictly on the evaluation JSON
Note: LLM is NOT used for grading/score calculation — only for text generation.
"""

import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Try to import Google Generative AI SDK (Gemini)
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except Exception:
    GENAI_AVAILABLE = False

# Helper to call Gemini (model: gemini-2.5-flash per user's requirement)
def call_gemini(prompt: str, max_output_tokens: int = 800, timeout: int = 30) -> Optional[str]:
    if not GENAI_AVAILABLE:
        logger.warning("Gemini SDK not available in environment.")
        return None
    api_key = os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("GENAI_API_KEY not set.")
        return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_output_tokens}
        )
        if response and hasattr(response, "text"):
            return response.text.strip()
        # some SDK versions return different structure
        if response and isinstance(response, dict) and response.get("candidates"):
            return response["candidates"][0].get("content", "").strip()
    except Exception as e:
        logger.exception("Gemini API call failed: %s", e)
    return None

# Generate test cases (LLM first, fallback second)
def generate_test_cases(code_text: str, max_cases: int = 6) -> List[str]:
    if not code_text.strip():
        return []

    # Prompt should be short & structured — LLM must return lines with input::expected_output
    prompt = (
        "You are an assistant that generates simple, deterministic input-output test cases "
        "for a C program. Return up to {max} test cases, one per line, in the format:\n"
        "input::expected_output\n\n"
        "Only provide plain lines of testcases — do not add commentary.\n\n"
        "C PROGRAM:\n"
        .format(max=max_cases) +
        code_text
    )

    text = call_gemini(prompt, max_output_tokens=400)
    if text:
        lines = [l.strip() for l in text.splitlines() if "::" in l and l.strip()]
        # Normalize spaces and limit to max_cases
        cleaned = []
        for ln in lines:
            if len(cleaned) >= max_cases:
                break
            cleaned.append(ln)
        if cleaned:
            logger.info("LLM produced %d test cases", len(cleaned))
            return cleaned

    # fallback heuristics (no LLM)
    logger.info("Falling back to heuristic test-case generator.")
    ct = code_text.lower()
    if "scanf" in ct and "printf" in ct and "+" in ct:
        return ["2 3::5", "10 15::25", "-5 5::0", "0 0::0"][:max_cases]
    if "factorial" in ct:
        return ["3::6", "5::120", "0::1"][:max_cases]
    if "average" in ct or "mean" in ct:
        return ["2 4::3", "10 20::15"][:max_cases]
    if "reverse" in ct:
        return ["123::321", "9870::789"][:max_cases]
    # generic fallback
    return ["1::1", "2::2"][:max_cases]

# Generate a detailed human-readable report from evaluation JSON
def generate_detailed_report(evaluation: Dict[str, Any]) -> str:
    """
    Send the evaluation JSON to the LLM with a prompt asking for a structured,
    actionable report. The LLM must not change scores; it only explains findings.
    """
    if not isinstance(evaluation, dict):
        return "Invalid evaluation context provided to report generator."

    # Use a dynamic prompt that includes the JSON (stringified)
    # Keep prompt explicit that LLM must NOT modify/override scores.
    prompt = (
        "You are an experienced C instructor. Using ONLY the evaluation JSON below, "
        "write a clear, structured, and actionable report for the student. "
        "Include sections: Summary (one-line), Compilation (errors/warnings), Static Analysis "
        "(issues and how to fix), Functional Testing (per-test outcomes and suggested fixes), "
        "Performance Notes, and Final Recommendations. Do NOT change the numerical scores; "
        "do NOT re-run or re-evaluate—only explain and provide improvement suggestions.\n\n"
        "EVALUATION_JSON:\n" + json_str(evaluation)
    )

    text = call_gemini(prompt, max_output_tokens=1000)
    if text:
        return text

    # Fallback textual report (no LLM)
    # Provide a structured fallback report using evaluation data
    lines = []
    lines.append("C PROGRAM EVALUATION REPORT (fallback, generated without LLM)\n")
    lines.append(f"Final Score: {evaluation.get('final_score', 0)}/100")
    # Compilation
    comp = evaluation.get("compile", {})
    if comp.get("status") == "success":
        lines.append("\nCompilation: ✅ Compiled successfully.")
    else:
        lines.append("\nCompilation: ❌ Compilation failed.")
        lines.append(f"Compiler stderr:\n{comp.get('stderr', '')}")
    # Static
    static = evaluation.get("static", {})
    issues = static.get("issues", [])
    if issues:
        lines.append("\nStatic Analysis: Issues found:")
        for it in issues:
            lines.append(f"- {it}")
    else:
        lines.append("\nStatic Analysis: No issues detected by heuristics/cppcheck.")
    # Tests
    t = evaluation.get("test", {})
    lines.append("\nFunctional Tests:")
    if t.get("total", 0) == 0:
        lines.append("No functional tests provided.")
    else:
        lines.append(f"Passed {t.get('passed',0)} / {t.get('total',0)} tests.")
        for idx, r in enumerate(t.get("results", []), start=1):
            lines.append(f"Test {idx}: input={r.get('input')} expected={r.get('expected')} got={r.get('actual')} -> {'PASS' if r.get('success') else 'FAIL'}")
    # Performance
    perf = evaluation.get("perf", {})
    lines.append("\nPerformance:")
    lines.append(perf.get("comment", "No performance data."))

    lines.append("\nRecommendations:")
    lines.append("- Fix compilation errors first.")
    lines.append("- Address static analyzer warnings (avoid unsafe functions).")
    lines.append("- Add edge-case tests and re-run.")
    return "\n".join(lines)

# small helper to stringify JSON safely (without importing json at top-level to keep file minimal)
def json_str(obj: Any) -> str:
    try:
        import json
        return json.dumps(obj, indent=2)
    except Exception:
        return str(obj)
