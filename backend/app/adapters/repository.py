from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from app.core.canonical import canonical_bytes, content_hash
from app.core.errors import ConflictError, NotFoundError
from app.domain.models import LearnerEvent, SessionRecord, Trace


class JsonRepository:
    """Single-process JSONL trial repository with restart-safe idempotency."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.events_dir = root / "events"
        self.sessions_dir = root / "sessions"
        self.results_dir = root / "turn_results"
        self.traces_dir = root / "traces"
        for directory in (
            self.events_dir,
            self.sessions_dir,
            self.results_dir,
            self.traces_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._event_adapter = TypeAdapter(LearnerEvent)

    @staticmethod
    def _safe(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _atomic_json(self, path: Path, value: Any) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_bytes(canonical_bytes(value))
        os.replace(temp, path)

    def append_event(self, event: LearnerEvent) -> tuple[LearnerEvent, bool]:
        path = self.events_dir / f"{self._safe(event.learner_id)}.jsonl"
        with self._lock:
            for existing in self.load_events(event.learner_id):
                if existing.idempotency_key == event.idempotency_key:
                    return existing, False
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(event.model_dump_json(exclude_none=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        return event, True

    def load_events(self, learner_id: str) -> list[LearnerEvent]:
        path = self.events_dir / f"{self._safe(learner_id)}.jsonl"
        if not path.exists():
            return []
        events: list[LearnerEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(self._event_adapter.validate_json(line))
        return events

    def save_session(self, session: SessionRecord) -> None:
        with self._lock:
            self._atomic_json(
                self.sessions_dir / f"{self._safe(session.session_id)}.json",
                session.model_dump(mode="json", exclude_none=True),
            )

    def load_session(self, session_id: str) -> SessionRecord:
        path = self.sessions_dir / f"{self._safe(session_id)}.json"
        if not path.exists():
            raise NotFoundError("SESSION_NOT_FOUND", "The requested session does not exist.")
        return SessionRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def save_trace(self, trace: Trace) -> None:
        with self._lock:
            self._atomic_json(
                self.traces_dir / f"{self._safe(trace.trace_id)}.json",
                trace.model_dump(mode="json", exclude_none=True),
            )

    def load_trace(self, trace_id: str) -> Trace:
        path = self.traces_dir / f"{self._safe(trace_id)}.json"
        if not path.exists():
            raise NotFoundError("TRACE_NOT_FOUND", "The requested trace does not exist.")
        return Trace.model_validate_json(path.read_text(encoding="utf-8"))

    def load_turn_result(self, session_id: str, client_turn_id: str, request: Any) -> dict | None:
        path = self.results_dir / f"{self._safe(session_id + '|' + client_turn_id)}.json"
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["request_hash"] != content_hash(request):
            raise ConflictError(
                "IDEMPOTENCY_KEY_REUSED",
                "The client turn ID was already used with a different payload.",
            )
        return record["response"]

    def save_turn_result(self, session_id: str, client_turn_id: str, request: Any, response: Any) -> None:
        path = self.results_dir / f"{self._safe(session_id + '|' + client_turn_id)}.json"
        with self._lock:
            self._atomic_json(
                path,
                {
                    "request_hash": content_hash(request),
                    "response": response.model_dump(mode="json", exclude_none=True),
                },
            )

