# ---------------------------------------------------------
# Configuration File for C Autograder Agentic Pipeline
# ---------------------------------------------------------

# -------------------------------
# LLM MODEL CONFIGURATIONS
# -------------------------------

MODEL_GROQ = "llama-3.1-8b-instant"
MODEL_GEMINI = "gemini-2.5-flash"


# -------------------------------
# SYSTEM LIMITS
# -------------------------------

MAX_TEST_CASES = 5
TEMP_DIR_PREFIX = "autograder_"


# -------------------------------
# ✅ UPDATED MARKING SCHEME (AS REQUIRED)
# -------------------------------

# Compilation Weight
WEIGHT_COMPILATION = 0.30

# Functional Test Weight
WEIGHT_FUNCTIONAL = 0.30

# Static Code Analysis Weight
WEIGHT_STATIC = 0.20

# Performance Evaluation Weight
WEIGHT_PERF = 0.20
