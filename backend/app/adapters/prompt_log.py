from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from app.core.canonical import content_hash
from app.domain.models import LessonPlan


class PromptLogStore:
    """Append-only JSONL audit log for the bounded renderer call."""

    schema_version = "1.0"

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def append(
        self,
        *,
        plan: LessonPlan,
        model: str,
        request: dict[str, Any],
        provider: str,
        provider_called: bool,
        outcome: Literal["success", "fallback", "skipped"],
        duration_ms: float,
        response: dict[str, Any] | None = None,
        error_type: str | None = None,
        skip_reason: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "schema_version": self.schema_version,
            "event_type": "llm_call" if provider_called else "llm_call_skipped",
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "prompt_log_id": f"pl_{uuid4().hex}",
            "provider": provider,
            "provider_called": provider_called,
            "outcome": outcome,
            "model": model,
            "plan_hash": plan.plan_hash,
            "input_hash": plan.input_hash,
            "request": request,
            "request_hash": content_hash(request),
            "response": response,
            "response_hash": content_hash(response) if response is not None else None,
            "validation_result": "pass" if outcome == "success" else "not_applicable",
            "error_type": error_type,
            "skip_reason": skip_reason,
            "duration_ms": round(duration_ms, 3),
            "privacy": {
                "learner_identifier_logged": False,
                "credentials_logged": False,
                "raw_learner_history_logged": False,
            },
        }
        encoded = json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        return record

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
