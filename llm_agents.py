# llm_agents.py

import os
import json
import logging
from typing import List, Dict, Any, Literal
from pydantic import BaseModel, Field

# LangChain Imports
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import JsonOutputParser

logger = logging.getLogger(__name__)

# --- Pydantic Schemas for Structured Output ---

class TestCase(BaseModel):
    """Schema for a single generated test case."""
    input: str = Field(description="The input string to be piped to the C program's stdin.")
    expected_output: str = Field(description="The exact expected output (stdout) for the given input.")

class TestCasesOutput(BaseModel):
    """Schema for the list of test cases from a generation agent."""
    tests: List[TestCase] = Field(description="A list of generated or repaired test cases.")
    reason: str = Field(description="Brief explanation of the logic used to generate or repair the tests.")
    status: Literal['success', 'fallback', 'repaired', 'repair_fail'] = Field(description="Status of the generation/repair process.")

class FinalReviewOutput(BaseModel):
    """Schema for the final report from the Reviewer Agent."""
    revised_score: float = Field(description="The final calculated score (0.0 to 1.0), possibly adjusted by the LLM.")
    summary: str = Field(description="A concise summary of the student's performance.")
    detailed_feedback: str = Field(description="Detailed, actionable feedback covering compilation, testing, quality, and performance.")
    passed_functional_check: bool = Field(description="True if the code passed all functional tests.")

# --- LLM Initializations ---
# Groq for fast, structured generation (Test Cases)
groq_llm = ChatGroq(
    temperature=0.0,
    model_name="llama3-8b-8192" 
)
# Gemini Flash for complex reasoning and detailed reporting
gemini_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.1
)

# --- Heuristic Fallback (Used when LLM fails) ---
def _heuristic_test_gen(code_text: str, max_cases: int = 5) -> List[TestCase]:
    # Simplified fallback logic
    tests = []
    if "scanf" in code_text and max_cases > 0:
        tests.append(TestCase(input="5 3", expected_output="8"))
        if max_cases > 1:
            tests.append(TestCase(input="10 0", expected_output="10"))
    elif max_cases > 0:
        tests.append(TestCase(input="", expected_output="Hello"))
    
    return tests[:max_cases]

# ---------------------------------------------------------------------
# AGENT FUNCTIONS (Nodes in the Graph)
# ---------------------------------------------------------------------

def TestGeneratorAgent(code_text: str) -> TestCasesOutput:
    """Agent to generate initial test cases for the C code."""
    parser = JsonOutputParser(pydantic_object=TestCasesOutput)
    # ... (prompt definition for test generation using groq_llm)
    prompt = PromptTemplate(
        template="""You are an expert Test Case Generator for C code. Analyze the C source code and generate a list of up to 5 diverse test cases (inputs and exact expected outputs) to fully test its functionality. CODE: --- {code_text} --- {format_instructions}""",
        input_variables=["code_text"],
        partial_variables={"format_instructions": parser.get_format_instructions()}
    )
    chain = prompt | groq_llm | parser
    
    try:
        result = chain.invoke({"code_text": code_text})
        return TestCasesOutput(status="success", **result)
    except OutputParserException as e:
        logger.warning(f"Groq Test Generator failed: {e}. Using heuristic fallback.")
        fallback_tests = _heuristic_test_gen(code_text, 5)
        return TestCasesOutput(
            tests=fallback_tests,
            reason=f"Groq failed ({e}); heuristic fallback used",
            status="fallback"
        )


def TestRepairAgent(code_text: str, test_info: Dict[str, Any]) -> TestCasesOutput:
    """Agent to analyze test failures (when 0/N passed) and generate revised test cases."""
    parser = JsonOutputParser(pydantic_object=TestCasesOutput)
    
    failed_tests = [t for t in test_info.get('test_results', []) if t.get('passed') is False]
    failure_summary = json.dumps(failed_tests, indent=2)
    
    prompt = PromptTemplate(
        template="""You are the Test Repair Agent. The student's C code failed ALL initial functional tests. Analyze the failures and, if the existing tests were clearly incorrect (e.g., incorrect expected output for a correct input), generate a *revised* list of up to 5 test cases. If the failures are due to a student code bug, return the original tests and explain the bug in your reasoning.
        C CODE: {code_text}
        FAILED TEST SUMMARY: {failure_summary}
        {format_instructions}
        """,
        input_variables=["code_text", "failure_summary"],
        partial_variables={"format_instructions": parser.get_format_instructions()}
    )

    chain = prompt | gemini_llm | parser # Using Gemini for deeper reasoning
    
    try:
        result = chain.invoke({"code_text": code_text, "failure_summary": failure_summary})
        return TestCasesOutput(status="repaired", **result)
    except Exception as e:
        logger.error(f"Gemini Test Repair Agent failed: {e}. Cannot repair tests.")
        return TestCasesOutput(tests=[], reason="Repair agent failed.", status="repair_fail")


def CompilationFailureReportAgent(compile_info: Dict[str, Any]) -> FinalReviewOutput:
    """Agent that generates a specialized report for a critical compilation failure."""
    parser = JsonOutputParser(pydantic_object=FinalReviewOutput)
    error_message = compile_info.get("stderr", "No compilation error message provided.")
    
    prompt = PromptTemplate(
        template="""You are a C Programming Tutor. The student's code failed to compile. Generate a detailed feedback report focusing ONLY on the compilation errors. The revised_score must be 0.0, and detailed_feedback must analyze the error messages and provide a concrete fix.
        COMPILATION ERROR MESSAGE: {error_message}
        {format_instructions}
        """,
        input_variables=["error_message"],
        partial_variables={"format_instructions": parser.get_format_instructions()}
    )
    
    chain = prompt | gemini_llm | parser
    
    try:
        result = chain.invoke({"error_message": error_message})
        # Force critical failure results
        result['revised_score'] = 0.0
        result['passed_functional_check'] = False
        return FinalReviewOutput(**result)
    except Exception as e:
        return FinalReviewOutput(
            revised_score=0.0,
            summary="Agent Failure: Could not generate report for compilation error.",
            detailed_feedback=f"Could not generate LLM report due to an internal error: {e}.",
            passed_functional_check=False
        )


def FinalReviewerAgent(full_evaluation_data: Dict[str, Any]) -> FinalReviewOutput:
    """Agent to generate the final report, review scores, and provide holistic feedback."""
    parser = JsonOutputParser(pydantic_object=FinalReviewOutput)

    initial_score = full_evaluation_data.get('final_score', 0.0)
    
    prompt = PromptTemplate(
        template="""You are the Final Reviewer Agent. Analyze the complete technical evaluation data for a C program and generate a final, polished report. You may slightly adjust the `initial_score` if the penalties seem overly harsh or lenient.
        FULL EVALUATION DATA (JSON): {evaluation_data}
        Initial Calculated Score: {initial_score} / 1.0
        {format_instructions}
        """,
        input_variables=["initial_score"],
        partial_variables={"format_instructions": parser.get_format_instructions(), 
                           "evaluation_data": json.dumps(full_evaluation_data, indent=2)}
    )

    chain = prompt | gemini_llm | parser
    
    try:
        result = chain.invoke({"initial_score": initial_score})
        # The result includes revised_score, summary, and detailed_feedback
        return FinalReviewOutput(**result)
    except Exception as e:
        test_results = full_evaluation_data.get('test_info', {}).get('test_results', [])
        return FinalReviewOutput(
            revised_score=initial_score,
            summary="Agent Failure: Could not generate report.",
            detailed_feedback=f"Could not generate LLM report due to an internal error: {e}. Raw data available.",
            passed_functional_check=all(t.get('passed', False) for t in test_results)
        )
