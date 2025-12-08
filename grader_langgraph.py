# grader_langgraph.py
# Clean, well-indented grader orchestrator for the C Autograder pipeline.
# - Computes final score using the configured weights
# - Calls compilation, testing, static analysis and perf tools
# - Handles compilation-failure path (partial marks)
# - Returns the exact keys expected by the rest of the app

from typing import Dict, Any

from config import (
    WEIGHT_COMPILATION,
    WEIGHT_FUNCTIONAL,
    WEIGHT_STATIC,
    WEIGHT_PERF,
)

# Import your agents/tools. These imports must match your repo.
# If any of these modules are named differently in your repo, update the names below.
from Llm_agents import (
    CompilationFailureReportAgent,
    FinalReviewAgent,
)
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
    """
    Compute final score using configured weights.
    Scores should be in 0.0 - 1.0 range.
    """
    final = (
        WEIGHT_COMPILATION * compile_score
        + WEIGHT_FUNCTIONAL * functional_score
        + WEIGHT_STATIC * static_score
        + WEIGHT_PERF * performance_score
    )
    return round(final, 3)


def run_grader_pipeline(user_code: str) -> Dict[str, Any]:
    """
    Run the full grading pipeline and return structured results.

    Returns a dict with keys used by app.py:
      - compile_info
      - test_info
      - static_info
      - perf_info
      - final_score
      - final_report (summary, detailed_feedback)
    """
    # 1) Compilation stage
    compile_info = compile_c_code_tool(user_code)

    # Initialize placeholders
    test_info: Dict[str, Any] = {}
    static_info: Dict[str, Any] = {}
    perf_info: Dict[str, Any] = {}

    # Default component scores
    compile_score = 1.0 if compile_info.get("status") == "success" else 0.0
    functional_score = 0.0
    static_score = 0.0
    performance_score = 0.0

    # 2) If compilation succeeded, run full pipeline
    if compile_info.get("status") == "success":
        # Functional testing
        test_info = run_test_cases_tool(compile_info)
        passed = test_info.get("passed_count", 0)
        total = test_info.get("total_count", 1)
        functional_score = (passed / total) if total > 0 else 0.0

        # Static analysis
        static_info = static_analysis_tool(user_code)
        issue_count = len(static_info.get("issues", []))
        # Each flagged issue deducts 0.2 from static_score, bounded to [0,1]
        static_score = max(0.0, 1.0 - (0.2 * issue_count))

        # Performance analysis
        perf_info = performance_analysis_tool(compile_info)
        # Here we keep performance_score = 1.0 as a baseline (adjust as needed)
        performance_score = 1.0

        # Compute final numeric score
        final_score = compute_final_score(
            compile_score,
            functional_score,
            static_score,
            performance_score,
        )

        # Final LLM review (Gemini) — returns dict with 'summary' and 'detailed_feedback'
        final_review = FinalReviewAgent(
            {
                "compile_info": compile_info,
                "test_info": test_info,
                "static_info": static_info,
                "perf_info": perf_info,
                "final_score": final_score,
            }
        )

    # 3) If compilation failed, award partial marks (static + perf) and create failure report
    else:
        # Still run static analysis (structural assessment)
        static_info = static_analysis_tool(user_code)
        issue_count = len(static_info.get("issues", []))
        static_score = max(0.0, 1.0 - (0.2 * issue_count))

        # Performance gets a structural default (adjustable)
        performance_score = 0.6

        # No functional execution possible
        functional_score = 0.0
        compile_score = 0.0

        # Final score uses only static and performance weights (per your policy)
        final_score = round(
            (WEIGHT_STATIC * static_score) + (WEIGHT_PERF * performance_score),
            3,
        )

        # LLM agent that generates a failure-style review and awards partials
        final_review = CompilationFailureReportAgent(
            compile_info=compile_info,
            static_score=static_score,
            perf_score=performance_score,
        )

    # Construct the returned structure exactly as expected by app.py
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
