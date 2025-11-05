# groq_llm.py
import os
import requests
import logging
import json

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def generate_test_cases_with_groq(code_text: str, max_cases: int = 8) -> dict:
    """
    Generate test cases using Groq API (model: openai/gpt-oss-120b).
    Uses completion-style request schema instead of chat schema.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"status": "error", "tests": [], "reason": "GROQ_API_KEY missing"}

    prompt = f"""
You are a precise test case generator for C programs.

Analyze the following code and produce up to {max_cases} test cases to verify its correctness.

Each test case should be one line:
<input_values>::<expected_output>

Use numeric examples. No markdown, no explanations.

C program:
{code_text}
"""

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "openai/gpt-oss-120b",
            "prompt": prompt,
            "temperature": 0.2,
            "max_tokens": 400
        }

        response = requests.post(
            "https://api.groq.com/openai/v1/completions",
            headers=headers,
            json=payload,
            timeout=40
        )

        logger.info(f"Groq API status: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"Groq error: {response.text[:300]}")
            return {"status": "error", "tests": [], "reason": f"Groq error {response.status_code}"}

        data = response.json()
        text = data.get("choices", [{}])[0].get("text", "").strip()
        if not text:
            logger.error(f"Groq OSS 20B returned no text. Full response: {json.dumps(data, indent=2)[:300]}")
            return {"status": "error", "tests": [], "reason": "Empty response from Groq"}

        lines = [ln.strip() for ln in text.splitlines() if "::" in ln]
        if lines:
            logger.info(f"Groq OSS 120B produced {len(lines)} test cases.")
            return {"status": "ok", "tests": lines[:max_cases], "reason": "Groq OSS 20B test generation successful"}

        logger.warning("Groq OSS 120B response had no valid test lines.")
        return {"status": "error", "tests": [], "reason": "No '::' formatted lines found"}

    except Exception as e:
        logger.error(f"Groq OSS 120B request failed: {e}")
        return {"status": "error", "tests": [], "reason": str(e)}
