"""Keep the test suite hermetic: force template mode so no test makes a live LLM
network call, regardless of which API keys are present in the environment/.env."""
import os

os.environ["LLM_DISABLED"] = "1"
