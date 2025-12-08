"""
Configuration constants for the C Autograder pipeline.
"""
# Model names
MODEL_GROQ = "llama-3.1-8b-instant"
MODEL_GEMINI = "gemini-2.5-flash"

# Maximum number of test cases to generate/repair
MAX_TEST_CASES = 5

# Temporary directory prefix for code compilation
TEMP_DIR_PREFIX = "autograder_"

# Scoring weights
WEIGHT_FUNCTIONAL = 0.50
WEIGHT_STATIC = 0.30
WEIGHT_PERF = 0.20
