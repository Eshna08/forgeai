"""Settings loaded ONLY from environment / .env. No key is ever hardcoded."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"
load_dotenv(ROOT / ".env", override=False)


@dataclass
class Settings:
    provider: str
    base_url: str
    api_key: str
    model: str
    judge_model: str
    temperature: float
    max_tokens_per_run: int
    max_seconds_per_run: float
    embedding_backend: str
    target_score: float
    runs_dir: Path
    request_timeout: float
    min_interval_s: float


def _f(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def get_settings() -> Settings:
    key = _f("LLM_API_KEY", "")
    base = _f("LLM_BASE_URL", "")
    # No provider configured and no endpoint at all -> mock, so a fresh checkout still runs.
    provider = _f("LLM_PROVIDER", "openai" if (key or base) else "mock").lower()
    model = _f("LLM_MODEL", "llama-3.1-8b-instant")
    return Settings(
        provider=provider,
        base_url=base or "https://api.openai.com/v1",
        api_key=key,
        model=model,
        judge_model=_f("JUDGE_MODEL", model),
        temperature=float(_f("LLM_TEMPERATURE", "0")),
        max_tokens_per_run=int(_f("MAX_TOKENS_PER_RUN", "600000")),
        max_seconds_per_run=float(_f("MAX_SECONDS_PER_RUN", "2400")),
        embedding_backend=_f("EMBEDDING_BACKEND", "auto").lower(),
        target_score=float(_f("TARGET_SCORE", "90")),
        runs_dir=Path(_f("RUNS_DIR", str(ROOT / "runs"))),
        request_timeout=float(_f("LLM_TIMEOUT", "60")),
        min_interval_s=float(_f("LLM_MIN_INTERVAL_S", "0")),
    )
