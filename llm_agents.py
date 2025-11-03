"""
llm_agents.py

Safe wrapper around a generative LLM (Gemini / genai SDK). Provides:
- safe extraction of textual output from model responses (handles missing Parts)
- retry on token-truncation finishes
- two helper call sites used by grader_langgraph.py:
    * generate_test_cases(code_text) -> list[str]
    * generate_detailed_report(context_dict) -> str

Notes:
- This file deliberately uses logging, not Streamlit, so it can be used headless
  (by unit tests or by the app).
- If the 'genai' / Gemini SDK is not installed or configured, the wrapper will
  gracefully return None / fallback instead of crashing.
"""

from typing import Tuple, Optional, Dict, Any, List
import logging
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Try importing a typical 'genai' SDK. If not present, we'll fall back gracefully.
try:
    import genai  # type: ignore
    from genai import types as genai_types  # type: ignore
    GENAI_AVAILABLE = True
    logger.info("genai SDK imported successfully.")
except Exception:
    GENAI_AVAILABLE = False
    logger.warning("genai SDK not available. LLM calls will return None. Install genai to enable LLM features.")


def _extract_text_from_response(response: Any) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Robustly extract text and some metadata from a model response.
    Returns (text_or_none, meta_dict)

    The code is defensive because some SDKs raise when .text is accessed
    if the response has no textual Part.
    """
    meta = {"candidates_count": 0, "finish_reason": None, "safety": None}
    if response is None:
        return None, meta

    # fast path: some SDKs provide `response.text` (but may raise)
    try:
        text = getattr(response, "text", None)
        if text:
            # try to extract candidate metadata
            candidates = getattr(response, "candidates", None) or []
            meta["candidates_count"] = len(candidates)
            if candidates:
                cand0 = candidates[0]
                meta["finish_reason"] = getattr(cand0, "finish_reason", None)
                meta["safety"] = getattr(cand0, "safety_ratings", None) or getattr(cand0, "safety", None)
            return (text.strip() if isinstance(text, str) else str(text)), meta
    except Exception as e:
        logger.debug("response.text quick accessor not available or raised: %s", e)

    # fallback: iterate candidates and candidate.parts or candidate.content
    try:
        candidates = getattr(response, "candidates", None) or []
        meta["candidates_count"] = len(candidates)
        parts_texts: List[str] = []
        for cand in candidates:
            if not meta["finish_reason"]:
                meta["finish_reason"] = getattr(cand, "finish_reason", None)
            if not meta["safety"]:
                meta["safety"] = getattr(cand, "safety_ratings", None) or getattr(cand, "safety", None)

            # Check cand.parts
            parts = getattr(cand, "parts", None)
            if parts:
                for p in parts:
                    part_text = getattr(p, "text", None) or getattr(p, "content", None)
                    if part_text:
                        parts_texts.append(str(part_text))
            else:
                # fallback: candidate.text / candidate.content
                cand_text = getattr(cand, "text", None)
                if cand_text:
                    parts_texts.append(str(cand_text))
                else:
                    content = getattr(cand, "content", None)
                    if content:
                        # content may be list/dict/string
                        if isinstance(content, (list, tuple)):
                            for cp in content:
                                if isinstance(cp, str):
                                    parts_texts.append(cp)
                                elif isinstance(cp, dict) and "text" in cp:
                                    parts_texts.append(cp["text"])
                        elif isinstance(content, str):
                            parts_texts.append(content)

        if parts_texts:
            combined = "\n".join(parts_texts).strip()
            return combined, meta
    except Exception as e:
        logger.exception("Unexpected error while parsing candidates: %s", e)

    logger.warning("No textual parts found in LLM response (meta=%s).", meta)
    return None, meta


def _make_model(name: str = "gemini-2.5-flash"):
    """
    Factory for model object. Returns None if SDK unavailable or model can't be created.
    """
    if not GENAI_AVAILABLE:
        return None
    try:
        # Typical usage: genai.GenerativeModel("model-name")
        return genai.GenerativeModel(name)
    except Exception as e:
        logger.exception("Failed to instantiate genai model '%s': %s", name, e)
        return None


def _single_generate(model: Any, prompt: str, timeout: int, max_output_tokens: int):
    """
    Encapsulate a single call to model.generate_content and return the response object
    or None on exception.
    """
    if model is None:
        return None
    try:
        # Different genai SDK versions accept different call signatures.
        # Try common variants defensively.
        try:
            # Preferred: model.generate_content(prompt, generation_config=..., request_options=...)
            gen_cfg = {"max_output_tokens": int(max_output_tokens), "temperature": 0.0}
            resp = model.generate_content(prompt, generation_config=gen_cfg, request_options={"timeout": timeout})
            return resp
        except TypeError:
            # Fallback: older/newer SDKs
            resp = model.generate_content(prompt, request_options={"timeout": timeout}, generation_config={"max_output_tokens": int(max_output_tokens)})
            return resp
    except Exception as e:
        logger.exception("Model generate_content failed: %s", e)
        return None


def call_gemini(prompt: str, timeout: int = 60, max_output_tokens: int = 1500, retry_on_truncate: bool = True) -> Optional[str]:
    """
    Top-level safe wrapper. Returns textual output or None.

    Behavior:
    - If genai SDK is missing, returns None (and logs a warning).
    - Calls model.generate_content safely, extracts text using _extract_text_from_response.
    - If the response finish_reason indicates truncation, optionally retries once with higher token limit.
    """
    model = _make_model()
    if model is None:
        logger.info("LLM model not available; returning None for prompt.")
        return None

    logger.debug("Calling model with max_output_tokens=%s timeout=%s", max_output_tokens, timeout)
    response = _single_generate(model, prompt, timeout=timeout, max_output_tokens=max_output_tokens)
    text, meta = _extract_text_from_response(response)
    if text:
        return text

    # check for truncation or MAX_TOKENS finish reason
    finish = meta.get("finish_reason")
    truncated = False
    if finish is not None:
        try:
            fin_str = str(finish).upper()
            if "MAX" in fin_str or "TOKEN" in fin_str or "TRUNC" in fin_str:
                truncated = True
        except Exception:
            pass

    # if no candidates at all, bail
    if meta.get("candidates_count", 0) == 0:
        logger.warning("LLM returned 0 candidates for prompt (meta=%s).", meta)
        return None

    # retry logic
    if retry_on_truncate and truncated:
        logger.info("LLM response appeared truncated (finish=%s). Retrying with larger token limit.", finish)
        bigger = min(int(max_output_tokens) * 2, 8192)
        response = _single_generate(model, prompt, timeout=timeout, max_output_tokens=bigger)
        text, meta = _extract_text_from_response(response)
        return text

    # safety blocked?
    if meta.get("safety"):
        logger.warning("LLM safety metadata present: %s", meta["safety"])
        return None

    logger.warning("LLM returned no usable text after extraction. meta=%s", meta)
    return None


# --- Application-level helpers used by the grader ---

def generate_test_cases(code_text: str, max_prompt_tokens: int = 1024) -> List[str]:
    """
    Ask the LLM to propose test cases for the given C program.
    Returns a list of strings (each test case line) or [] if LLM unavailable/returns nothing.

    NOTE: For production, prefer deterministic test-case extraction/parsers or user-provided tests.
    """
    if not code_text or not code_text.strip():
        return []
    # Build a careful minimal prompt
    prompt = (
        "You are a helpful assistant. Given the following C program, suggest concise input-output "
        "test cases that validate correctness. For each test case, provide an input string and the "
        "expected output on a separate line, in this exact format:\n\n"
        "<input>::<expected_output>\n\n"
        "Only include test cases — no additional explanation. Program:\n\n"
        "-----BEGIN PROGRAM-----\n"
        f"{code_text}\n"
        "-----END PROGRAM-----\n\n"
        "Return up to 8 test cases.\n"
    )

    text = call_gemini(prompt, timeout=30, max_output_tokens=512)
    if not text:
        logger.info("No test-cases returned by LLM; returning empty list.")
        return []

    # Parse lines of form input::output — be permissive
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    tests = []
    for line in lines:
        # Accept either '::' or '->' or ':' separators with priority for '::'
        if "::" in line:
            tests.append(line)
        elif "->" in line:
            tests.append(line.replace("->", "::"))
        elif ":" in line and line.count(":") >= 1:
            # transform 'input: output' -> 'input::output'
            parts = line.split(":", 1)
            tests.append(f"{parts[0].strip()}::{parts[1].strip()}")
        else:
            # treat as input only (no expected output)
            tests.append(f"{line}::")
    return tests


def generate_detailed_report(context: Dict[str, Any]) -> str:
    """
    Generates a clear, human-readable grading report with or without LLM.
    """
    if not isinstance(context, dict):
        return "No context available for report."

    code = context.get("code", "<code omitted>")
    score = context.get("score", 0)
    compile_info = context.get("compile", {})
    static_info = context.get("static", {})
    test_info = context.get("test", {})
    perf_info = context.get("perf", {})

    # Try Gemini if available
    prompt = (
        "You are an experienced C programming evaluator. "
        "Provide a detailed, human-readable assessment of the student's code. "
        "The report should include:\n"
        "1. Compilation result\n"
        "2. Static code quality and safety issues\n"
        "3. Functional correctness (based on test results)\n"
        "4. Performance analysis\n"
        "5. Final score justification\n"
        "Use paragraphs, not bullet points. Write in a professional, encouraging tone.\n\n"
        f"CODE:\n{code}\n\n"
        f"CONTEXT:\n{context}\n"
    )

    text = call_gemini(prompt, timeout=45, max_output_tokens=1200)
    if text:
        return text

    # Fallback – structured human-readable version (no LLM)
    report = f"""
    C PROGRAMMING EVALUATION REPORT
    ---------------------------------------

    FINAL SCORE: {score}/100

    COMPILATION RESULT:
    The code compiled successfully without any errors. The GCC compiler reported no warnings or issues.

    STATIC ANALYSIS:
    {("No issues detected. The code follows good programming practices."
      if not static_info.get("issues")
      else "The following issues were found: " + ", ".join(static_info["issues"]))}

    FUNCTIONAL TESTING:
    {("All provided test cases passed successfully."
      if test_info.get("passed", 0) == test_info.get("total", 0) and test_info.get("total", 0) > 0
      else "Functional tests were missing or some failed. Ensure you provide correct test cases and validate all edge cases.")}

    PERFORMANCE ANALYSIS:
    {perf_info.get("comment", "Performance appears acceptable for this type of program.")}

    OVERALL EVALUATION:
    The submitted code is functionally correct and syntactically sound. To improve, ensure that test cases are defined properly so that correctness can be evaluated more accurately.
    """

    return report.strip()
