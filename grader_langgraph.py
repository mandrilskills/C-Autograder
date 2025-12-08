# grader_langgraph.py
# ---------------------------------------------------------
# Clean, crash-proof grader pipeline with correct imports
# ---------------------------------------------------------

from typing import Dict, Any

from config import (
    WEIGHT_COMPILATION,
    WEIGHT_FUNCTIONAL,
    WEIGHT_STATIC,
    WEIGHT_PERF,
)

# ✅ FIXED CASE (llm_agents, NOT Llm_agents)
from llm_agents import (
    CompilationFailureReportAgent,
    FinalReviewAgent,
)

# ✅ Your existing tooling layer
from tools import (
    compile_c_code_tool,
    run_test_cases_tool,
    static_analysis_tool,
    performance_analysis_tool,
)


def compute_final_score(
    compile_score: float,
    functional_score: float,
    static_score: float,
    performance_score: float,
) -> float:
    return round(
        WEIGHT_COMPILATION * compile_score
        + WEIGHT_FUNCTIONAL * functional_score
        + WEIGHT_STATIC * static_score
        + WEIGHT_PERF * performance_score,
        3,
    )


def run_grader_pipeline(user_code: str) -> Dict[str, Any]:
    # -------------------------------
    # 1. Compilation
    # -------------------------------
    compile_info = compile_c_code_tool(user_code)

    test_info: Dict[str, Any] = {}
    static_info: Dict[str, Any] = {}
    perf_info: Dict[str, Any] = {}

    compile_score = 1.0 if compile_info.get("status") == "success" else 0.0
    functional_score = 0.0
    static_score = 0.0
    performance_score = 0.0

    # -------------------------------
    # ✅ Compilation Success Path
    # -------------------------------
    if compile_info.get("status") == "success":

        test_info = run_test_cases_tool(compile_info)
        passed = test_info.get("passed_count", 0)
        total = test_info.get("total_count", 1)
        functional_score = (passed / total) if total > 0 else 0.0

        static_info = static_analysis_tool(user_code)
        issue_count = len(static_info.get("issues", []))
        static_score = max(0.0, 1.0 - (0.2 * issue_count))

        perf_info = performance_analysis_tool(compile_info)
        performance_score = 1.0

        final_score = compute_final_score(
            compile_score,
            functional_score,
            static_score,
            performance_score,
        )

        final_review = FinalReviewAgent(
            {
                "compile_info": compile_info,
                "test_info": test_info,
                "static_info": static_info,
                "perf_info": perf_info,
                "final_score": final_score,
            }
        )

    # -------------------------------
    # ✅ Compilation Failure → PARTIAL MARKING
    # -------------------------------
    else:

        static_info = static_analysis_tool(user_code)
        issue_count = len(static_info.get("issues", []))
        static_score = max(0.0, 1.0 - (0.2 * issue_count))

        performance_score = 0.6
        functional_score = 0.0
        compile_score = 0.0

        final_score = round(
            (WEIGHT_STATIC * static_score) +
            (WEIGHT_PERF * performance_score),
            3,
        )

        final_review = CompilationFailureReportAgent(
            compile_info=compile_info,
            static_score=static_score,
            perf_score=performance_score,
        )

    return {
        "compile_info": compile_info,
        "test_info": test_info,
        "static_info": static_info,
        "perf_info": perf_info,
        "final_score": final_score,
        "final_report": {
            "summary": final_review.get("summary"),
            "detailed_feedback": final_review.get("detailed_feedback"),
        },
    }
