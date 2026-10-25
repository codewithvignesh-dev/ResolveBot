"""Environment-backed settings. Read at call time so tests can override env vars."""
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    policies_path: str
    manifest_path: str
    db_path: str
    app_today: date
    llm_provider: str
    llm_model: str
    llm_api_key: str
    llm_base_url: str
    llm_timeout: float
    total_budget: float
    max_tool_calls: int


_DEFAULT_MODELS = {"groq": "llama-3.3-70b-versatile"}


def get_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    key = os.getenv(f"{provider.upper()}_API_KEY") or os.getenv("LLM_API_KEY", "")
    return Settings(
        policies_path=os.getenv("POLICIES_PATH", "./data/policies.md"),
        manifest_path=os.getenv("MANIFEST_PATH", "./data/manifest.json"),
        db_path=os.getenv("DB_PATH", "./data/shopsphere.db"),
        app_today=date.fromisoformat(os.getenv("APP_TODAY", "2026-07-01")),
        llm_provider=provider,
        llm_model=os.getenv("LLM_MODEL") or _DEFAULT_MODELS.get(provider, ""),
        llm_api_key=key,
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
        llm_timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "20")),
        total_budget=float(os.getenv("TOTAL_BUDGET_SECONDS", "26")),
        max_tool_calls=int(os.getenv("MAX_TOOL_CALLS", "6")),
    )
