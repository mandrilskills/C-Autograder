# llm_agents_langchain.py
import os
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import JsonOutputParser

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------- API KEY CHECK (Optional but Recommended) ----------------
# LangChain loads these automatically, but checking helps debugging.
if not os.getenv("GOOGLE_API_KEY"):
    logger.warning("GOOGLE_API_KEY environment variable not set.")
if not os.getenv("GROQ_API_KEY"):
    logger.warning("GROQ_API_KEY environment variable not set.")


# ---------------- HEURISTIC FALLBACK (Unchanged) ----------------
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


# ---------------- GEMINI REPORT GENERATION (LangChain) ----------------
def generate_llm_report(evaluation: dict) -> str:
    """Generate detailed evaluation report using Gemini 2.5 Flash via LangChain."""
    
    # CRITICAL FIX: Use the correct model name 'gemini-2.5-flash'
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            max_output_tokens=900,
            # Good practice for Gemini to handle system prompts
            convert_system_message_to_human=True 
        )
        
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", """
You are an expert C programming evaluator.
Analyze the following evaluation JSON and write a structured report with:
1. Summary
2. Compilation Details
3. Static Analysis
4. Functional Testing
5. Performance Evaluation
6. Recommendations
"""),
            ("human", "Evaluation JSON:\n{eval_json_str}")
        ])
        
        chain = prompt_template | llm
        
        report = chain.invoke({"eval_json_str": str(evaluation)})
        
        return report.content or "(LLM report generation failed: Gemini returned empty content.)"

    except Exception as e:
        logger.warning(f"Gemini (LangChain) failed: {e}")
        return f"(LLM report generation failed: {e})"


# ---------------- TEST CASE GENERATION (LangChain Groq) ----------------
def generate_test_cases_with_logging(code_text: str, max_cases: int = 8) -> dict:
    """Uses Groq API (via LangChain) for test case generation."""
    
    # Using a standard, fast Groq model
    try:
        llm = ChatGroq(model_name="llama3-8b-8192")
        
        system_prompt = f"""
You are a test case generator. Given the C code, generate {max_cases} test cases.
Format your response as a valid JSON object with a single key "tests", 
which is an array of strings.
Each string must be in the format 'input::expected_output'.
Do not provide any other text, just the JSON.
"""
        
        human_prompt = f"C Code:\n{code_text}"
        
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", human_prompt)
        ])
        
        # We chain the model to a JSON parser
        parser = JsonOutputParser()
        chain = prompt_template | llm | parser

        # Invoke the chain
        response_json = chain.invoke({})
        
        if response_json and "tests" in response_json and response_json["tests"]:
            logger.info(f"Groq (LangChain) succeeded in generating {len(response_json['tests'])} tests.")
            return {
                "status": "ok",
                "tests": response_json["tests"][:max_cases], # Ensure we don't exceed max_cases
                "reason": "Groq (LangChain) success",
            }
        else:
            raise Exception("Groq returned invalid or empty JSON.")

    except (Exception, OutputParserException) as e:
        logger.warning(f"Groq (LangChain) failed: {e}. Using heuristic fallback.")
        return {
            "status": "fallback",
            "tests": _heuristic_test_gen(code_text, max_cases),
            "reason": f"Groq (LangChain) failed: {e}; heuristic fallback used",
        }


# ---------------- CONNECTION TEST (LangChain) ----------------
def test_gemini_connection() -> str:
    """Quick diagnostic for Gemini 2.5 Flash via LangChain."""
    try:
        # CRITICAL FIX: Use the correct model name 'gemini-2.5-flash'
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
        response = llm.invoke("Say 'Gemini 2.5 Flash (LangChain) connection successful.'")
        return f"Gemini (LangChain) Response: {response.content}"
    except Exception as e:
        return f"Gemini (LangChain) connection failed: {e}"

# --- Example of how to run the test ---
if __name__ == "__main__":
    print("Testing connections...")
    print(test_gemini_connection())
    
    # Test Groq
    print("\nTesting Groq Test Case Generation...")
    test_code = "int main() { int a, b; scanf(\"%d %d\", &a, &b); printf(\"%d\", a + b); return 0; }"
    test_cases_result = generate_test_cases_with_logging(test_code)
    print(f"Status: {test_cases_result['status']}")
    print(f"Tests: {test_cases_result['tests']}")
