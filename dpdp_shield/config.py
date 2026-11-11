"""Central configuration. All secrets come from the environment / .env (never hardcoded)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = ""
    # Gemini 1.5 models have been retired; override via GEMINI_MODEL if you prefer another.
    gemini_model: str = "gemini-3.8-flash"
    gemini_embed_model: str = "gemini-embedding-001"
    gemini_fallback_model: str = ""  # optional; used if the main model keeps failing
    gemini_query_model: str = ""  # optional faster model for chat answers (default: gemini_model)
    embeddings_backend: str = "auto"  # auto | gemini | local
    data_dir: Path = ROOT / "data"
    kb_dir: Path = ROOT / "knowledge_base"
    chunk_tokens: int = 500
    chunk_overlap_tokens: int = 50
    top_k: int = 5
    max_pdf_pages: int = 50
    max_pdf_mb: int = 20
    llm_timeout_s: float = 20.0
    review_timeout_s: float = 60.0
    max_policy_chars_for_llm: int = 60_000

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", cls.gemini_model),
            gemini_embed_model=os.getenv("GEMINI_EMBED_MODEL", cls.gemini_embed_model),
            gemini_fallback_model=os.getenv("GEMINI_FALLBACK_MODEL", "").strip(),
            gemini_query_model=os.getenv("GEMINI_QUERY_MODEL", "").strip(),
            embeddings_backend=os.getenv("EMBEDDINGS_BACKEND", "auto").lower(),
            data_dir=Path(os.getenv("DATA_DIR", str(ROOT / "data"))),
            kb_dir=Path(os.getenv("KB_DIR", str(ROOT / "knowledge_base"))),
            top_k=_int("TOP_K", 5),
            llm_timeout_s=float(_int("LLM_TIMEOUT_S", 20)),
            review_timeout_s=float(_int("LLM_REVIEW_TIMEOUT_S", 60)),
            max_pdf_pages=_int("MAX_PDF_PAGES", 50),
        )
