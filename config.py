"""
Configuration constants for the C Autograder pipeline.
"""

MODEL_GROQ = "llama-3.1-8b-instant"
MODEL_GEMINI = "gemini-2.5-flash"

MAX_TEST_CASES = 5
TEMP_DIR_PREFIX = "autograder_"

# ✅ UPDATED MARKING SCHEME
WEIGHT_COMPILATION = 0.30
WEIGHT_FUNCTIONAL = 0.30
WEIGHT_STATIC = 0.20
WEIGHT_PERF = 0.20
