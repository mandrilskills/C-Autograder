# openai_oss_llm.py
import os
import requests
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def generate_test_cases_with_openai_oss(code_text: str, max_cases: int = 8) -> dict:
    """
    Generate test cases using OpenAI OSS 20B (gpt-oss-20b) model.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"status": "error", "tests": [], "reason": "GROQ_API_KEY missing"}

    prompt = f"""
You are a precise C test case generator.

Analyze the following C program and produce up to {max_cases} realistic test cases
to verify its correctness.

Each line should be formatted exactly as:
<input_values>::<expected_output>

Do not include explanations, markdown, or comments.

C program:
{code_text}
"""

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "gpt-oss-20b",
            "messages": [
                {"role": "system", "content": "You are a C program test-case generator."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 500
        }

        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=40
        )

        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            lines = [ln.strip() for ln in content.splitlines() if "::" in ln]
            if lines:
                logger.info(f"OSS 20B produced {len(lines)} test cases.")
                return {"status": "ok", "tests": lines[:max_cases], "reason": "OSS 20B test generation successful"}
            else:
                logger.warning("OSS 20B returned text but no test cases.")
        else:
            logger.error(f"OSS API error {resp.status_code}: {resp.text[:200]}")

    except Exception as e:
        logger.error(f"OSS test generation failed: {e}")

    return {"status": "fallback", "tests": [], "reason": "OSS 20B returned none or failed"}
