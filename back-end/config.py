"""Settings read once at start-up. Other modules use `config.NAME` so tests can override values."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")

DATABASE_ENABLED = bool(os.getenv("DATABASE_URL")) and os.getenv("APP_USE_IN_MEMORY_DB") != "1"
STATIC_DIR = PROJECT_DIR / "front-end"
MAX_DIETITIAN_DOCUMENT_BYTES = 10 * 1024 * 1024
OLLAMA_REQUEST_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))
