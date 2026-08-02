"""
Central configuration for the agent.
All environment-dependent values live here so tools/agent.py never
hardcode paths, keys, or model names.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# --- LLM config -------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")


def require_groq_api_key() -> str:
    """Return the Groq API key or raise a setup-focused error."""
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to .env or export it before running the agent."
        )
    return GROQ_API_KEY


# --- Google Sheets config ----------------------------------------------
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE", str(BASE_DIR / "service_account.json")
)

GOOGLE_SHARE_WITH_EMAIL = os.getenv("GOOGLE_SHARE_WITH_EMAIL") 

# --- Behavior knobs --------------------------------------------------
MAX_TOOL_RETRIES = int(os.getenv("MAX_TOOL_RETRIES", "2"))
DEFAULT_ROW_COUNT = int(os.getenv("DEFAULT_ROW_COUNT", "25"))

# --- Logging ------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- File paths ----------------------------------------------------------
DEFAULT_CSV_PATH = DATA_DIR / "employees.csv"
DEFAULT_XLSX_PATH = DATA_DIR / "employees.xlsx"
