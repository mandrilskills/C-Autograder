# llm_agents.py (Robust Gemini + Logging)
import os, logging, json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except Exception:
    GENAI_AVAILABLE = False

def call_gemini(prompt: str, max_output_tokens=800) -> Optional[str]:
    if not GENAI_AVAILABLE:
        logger.warning("Gemini SDK not available.")
        return None
    api_key = os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("API key not set.")
        return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        resp = model.generate_content(prompt, generation_config={"max_output_tokens": max_output_tokens})
        if hasattr(resp, "text") and resp.text:
            return resp.text.strip()
        if hasattr(resp, "candidates") and resp.candidates:
            cand = resp.candidates[0]
            if hasattr(cand, "content") and hasattr(cand.content.parts[0], "text"):
                return cand.content.parts[0].text.strip()
        logger.warning("Gemini returned empty response.")
    except Exception as e:
        logger.exception("Gemini error: %s", e)
    return None

def generate_test_cases(code: str, max_cases=6) -> List[str]:
    prompt = (
        "Generate up to {max_cases} practical input/output test cases for the following C code. "
        "Return them in any readable format — JSON, plain text, or structured pairs. Do NOT explain.\n\n"
        f"{code}"
    )
    txt = call_gemini(prompt, max_output_tokens=400)
    if txt:
        logger.info("Gemini produced test cases:\n%s", txt[:300])
        return txt.strip().splitlines()
    return []

def generate_detailed_report(evaluation: Dict[str, Any]) -> str:
    prompt = (
        "You are an experienced C programming evaluator. Based on the JSON evaluation below, "
        "write a detailed report with sections: Summary, Compilation, Static Analysis, Testing, Performance, "
        "and Recommendations. Keep technical accuracy, and do not re-evaluate numeric scores. If possible give a better code to the user\n\n"
        f"JSON:\n{json.dumps(evaluation, indent=2)}"
    )
    txt = call_gemini(prompt, max_output_tokens=1000)
    if txt:
        return txt
    # fallback
    return f"Fallback report. Evaluation Summary:\nScore: {evaluation.get('final_score', 0)}"
