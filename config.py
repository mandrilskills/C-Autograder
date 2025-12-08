# config.py
# Centralized configuration for the C autograder.

MODEL_GROQ = "llama-3.1-8b-instant"  # kept for consistency (not used in local-only mode)
MODEL_GEMINI = "gemini-2.5-flash"

# Limits & behavior
MAX_TEST_CASES = 5
TEMP_DIR_PREFIX = "autograder_"
COMPILE_TIMEOUT = 20        # seconds allowed for gcc
RUN_TIMEOUT = 2            # seconds per test run
CPPcheck_TIMEOUT = 10      # seconds for cppcheck

# Scoring weights (must sum to 1.0)
WEIGHT_FUNCTIONAL = 0.50
WEIGHT_STATIC = 0.30
WEIGHT_PERF = 0.20

# Partial credit rules
PARTIAL_ON_COMPILE_FAIL = True  # Award partial marks based on heuristics when compilation fails
