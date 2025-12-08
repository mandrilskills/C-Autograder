# ---------------------------------------------------------
# LLM AGENTS FOR C AUTOGRADER (GEMINI + GROQ)
# ---------------------------------------------------------

from typing import Dict, Any
from langchain.prompts import PromptTemplate
from langchain.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from config import MODEL_GEMINI, WEIGHT_STATIC, WEIGHT_PERF
from llm_loader import gemini_llm, groq_llm


# ---------------------------------------------------------
# ✅ FINAL REVIEW OUTPUT SCHEMA (UNCHANGED)
# ---------------------------------------------------------

class FinalReviewOutput(BaseModel):
    summary: str = Field(description="Short evaluation summary")
    detailed_feedback: str = Field(description="Detailed multi-point feedback")
    revised_score: float = Field(description="Revised final score after LLM review")
    passed_functional_check: bool = Field(description="Whether key logic passed")


# ---------------------------------------------------------
# ✅ FINAL REVIEW AGENT (UNCHANGED BEHAVIOUR)
# ---------------------------------------------------------

def FinalReviewAgent(full_eval_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Final holistic evaluation using Gemini 2.5 Flash after
    successful compilation & functional testing.
    """

    parser = JsonOutputParser(pydantic_object=FinalReviewOutput)

    prompt = PromptTemplate(
        template=(
            "You are a strict university-level examiner evaluating a C program.\n\n"
            "Compilation Info:\n{compile_info}\n\n"
            "Functional Test Results:\n{test_info}\n\n"
            "Static Analysis:\n{static_info}\n\n"
            "Performance Metrics:\n{perf_info}\n\n"
            "Final Numeric Score (pre-LLM): {final_score}\n\n"
            "Now generate:\n"
            "1. A short exam-style summary\n"
            "2. Detailed bullet-point feedback\n"
            "3. Decide if core logic passed\n\n"
            "{format_instructions}"
        ),
        input_variables=["compile_info", "test_info", "static_info", "perf_info", "final_score"],
        partial_variables={"format_instructions": parser.get_format_instructions()}
    )

    chain = prompt | gemini_llm | parser

    result = chain.invoke({
        "compile_info": full_eval_data.get("compile_info"),
        "test_info": full_eval_data.get("test_info"),
        "static_info": full_eval_data.get("static_info"),
        "perf_info": full_eval_data.get("perf_info"),
        "final_score": round(full_eval_data.get("final_score", 0.0), 3)
    })

    return {
        "summary": result.summary,
        "detailed_feedback": result.detailed_feedback,
        "revised_score": result.revised_score,
        "passed_functional_check": result.passed_functional_check
    }


# ---------------------------------------------------------
# ✅ ✅ ✅ COMPILATION FAILURE AGENT (REQUIRED CHANGE APPLIED)
# ---------------------------------------------------------
# 🔴 OLD BEHAVIOUR:
# revised_score = 0.0   ❌❌❌
#
# ✅ NEW BEHAVIOUR:
# Partial marks awarded using STATIC + PERFORMANCE
# ---------------------------------------------------------

def CompilationFailureReportAgent(
    compile_info: Dict[str, Any],
    static_score: float = 0.6,
    perf_score: float = 0.6
) -> Dict[str, Any]:
    """
    Generates a failure report when compilation fails,
    but still awards PARTIAL MARKS based on static structure
    and performance potential.
    """

    parser = JsonOutputParser(pydantic_object=FinalReviewOutput)

    error_message = compile_info.get("stderr", "No compilation error message provided.")

    prompt = PromptTemplate(
        template=(
            "The student's C program FAILED TO COMPILE.\n\n"
            "However, you must:\n"
            "• Analyze the compilation error\n"
            "• Assess logical structure from visible code\n"
            "• Judge algorithm intent\n"
            "• Apply university-style STEP MARKING\n\n"
            "Award PARTIAL MARKS for:\n"
            "• Static structure\n"
            "• Algorithm design intent\n\n"
            "DO NOT give full zero unless logic is completely meaningless.\n\n"
            "COMPILATION ERROR MESSAGE:\n{error_message}\n\n"
            "{format_instructions}"
        ),
        input_variables=["error_message"],
        partial_variables={"format_instructions": parser.get_format_instructions()}
    )

    chain = prompt | gemini_llm | parser

    result = chain.invoke({
        "error_message": error_message
    })

    # ✅ ✅ ✅ PARTIAL MARKS COMPUTATION (STATIC + PERFORMANCE ONLY)
    revised_score = round(
        (WEIGHT_STATIC * static_score) +
        (WEIGHT_PERF * perf_score),
        3
    )

    return {
        "summary": result.summary,
        "detailed_feedback": result.detailed_feedback,
        "revised_score": revised_score,
        "passed_functional_check": False
    }
