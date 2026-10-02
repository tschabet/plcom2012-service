"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    #: If set, every POST requires the header ``X-API-Key: <value>``.
    api_key: str | None = None
    #: Base for canonical URLs (CodeSystem, Questionnaire). Set this to your own namespace.
    canonical_base: str = "https://example.org/fhir"
    #: Optional JSON file overriding the linkIds the service reads (see README).
    linkid_map_path: str | None = None
    #: Requests larger than this are rejected with 413.
    max_body_bytes: int = 262_144

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            api_key=os.environ.get("PLCOM_API_KEY") or None,
            canonical_base=os.environ.get("PLCOM_CANONICAL_BASE", cls.canonical_base).rstrip("/"),
            linkid_map_path=os.environ.get("PLCOM_LINKID_MAP") or None,
            max_body_bytes=int(os.environ.get("PLCOM_MAX_BODY_BYTES", cls.max_body_bytes)),
        )
