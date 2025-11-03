# groq_llm.py
import os
import requests
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def generate_test_cases_with_groq(code_text: str, max_cases: int = 8) -> dict:
    """
    Generate test cases using Groq LLM (Mixtral-8x7b or Llama3 via Groq API).
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"status": "error", "tests": [], "reason": "GROQ_API_KEY missing"}

    prompt = f"""
You are a precise C test case generator.

Analyze the following C program and produce up to {max_cases} test cases
to verify its correctness.

Each test case must be one line:
<input_values>::<expected_output>

Use realistic numeric examples.
Do NOT include explanations, comments, or markdown formatting.

C program:
{code_text}
"""

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "mixtral-8x7b",
            "messages": [
                {"role": "system", "content": "You are a code test-case generator."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 400
        }

        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )

        if resp.status_code == 200:
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            lines = [ln.strip() for ln in text.splitlines() if "::" in ln]
            if lines:
                logger.info(f"Groq generated {len(lines)} test cases.")
                return {"status": "ok", "tests": lines[:max_cases], "reason": "Groq test generation successful"}
        else:
            logger.error(f"Groq API error {resp.status_code}: {resp.text}")

    except Exception as e:
        logger.error(f"Groq test generation failed: {e}")

    return {"status": "fallback", "tests": [], "reason": "Groq returned none or failed"}
