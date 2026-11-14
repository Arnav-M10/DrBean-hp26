"""Explicit local deployment configuration. No remote-to-local fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: str = "var/bean.sqlite3"
    blob_dir: str = "var/sources"
    auth_file: str = "var/auth.json"
    auth_tokens: dict[str, str] = field(default_factory=dict, repr=False)
    allowed_origins: tuple[str, ...] = ("http://localhost:8000", "http://127.0.0.1:8000")
    max_json_bytes: int = 262_144
    max_upload_bytes: int = 5 * 1024 * 1024
    artifact_dir: str = "var/artifacts"
    science_adapter: str = "counterdex"
    counterdex_python: str = "python3.11"
    source_intake_mode: str = "disabled"
    controlled_source_manifest_path: str | None = None

    def __post_init__(self):
        if self.source_intake_mode not in {"disabled", "controlled"}:
            raise ValueError("Source intake mode must be disabled or controlled")
        if self.source_intake_mode == "controlled" and not self.controlled_source_manifest_path:
            raise ValueError("Controlled intake requires an explicit trusted local fixture manifest")

    @classmethod
    def from_env(cls) -> Settings:
        if os.getenv("DATABASE_URL"):
            raise ValueError("This lane supports local SQLite only; DATABASE_URL cannot silently fall back.")
        auth_file = os.getenv("BEAN_AUTH_FILE", "var/auth.json")
        raw = os.getenv("BEAN_AUTH_TOKENS_JSON")
        if raw is None and Path(auth_file).is_file():
            raw = Path(auth_file).read_text(encoding="utf-8")
        tokens = json.loads(raw) if raw else {}
        if not isinstance(tokens, dict) or any(
            not isinstance(actor, str) or not actor or not isinstance(token, str) or len(token) < 32
            for actor, token in tokens.items()
        ):
            raise ValueError("Authentication must map actor names to bearer tokens of at least 32 characters.")
        return cls(
            database_path=os.getenv("BEAN_DATABASE_PATH", "var/bean.sqlite3"),
            blob_dir=os.getenv("BEAN_BLOB_DIR", "var/sources"),
            auth_file=auth_file,
            auth_tokens=tokens,
            artifact_dir=os.getenv("BEAN_ARTIFACT_DIR", "var/artifacts"),
            science_adapter=os.getenv("BEAN_SCIENCE_ADAPTER", "counterdex"),
            counterdex_python=os.getenv("BEAN_COUNTERDEX_PYTHON", "python3.11"),
            source_intake_mode=os.getenv("BEAN_SOURCE_INTAKE_MODE", "disabled"),
            controlled_source_manifest_path=os.getenv("BEAN_CONTROLLED_SOURCE_MANIFEST"),
            allowed_origins=tuple(
                origin.strip() for origin in os.getenv(
                    "BEAN_ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
                ).split(",") if origin.strip()
            ),
        )
