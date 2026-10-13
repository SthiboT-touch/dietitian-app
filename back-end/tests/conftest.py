import os

# Keep test runs out of the LangSmith project; load_dotenv does not override variables already set.
os.environ["LANGSMITH_TRACING"] = "false"
