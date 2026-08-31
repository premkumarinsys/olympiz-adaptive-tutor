from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from app.domain.models import (
    Activity,
    LearnerEvent,
    LearnerState,
    LessonPlan,
    Outcome,
    Placement,
    PolicyDecision,
    StrictModel,
)


class Day0StartRequest(StrictModel):
    learner_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    exam_goal: Literal["NEET", "JEE Main", "JEE Advanced", "olympiad", "exploring"]
    topic_id: Literal["newton_second_law"] = "newton_second_law"
    language: Literal["en"] = "en"
    accessibility: tuple[str, ...] = ()
    pace_preference: Literal["quick", "careful"] = "careful"
    idempotency_key: str = Field(min_length=1, max_length=120)


class DayNStartRequest(StrictModel):
    memory_fixture_id: str | None = None
    memory_bundle: MemoryBundle | None = None
    topic_id: str | None = None
    session_goal: str = "practice"

    @model_validator(mode="after")
    def exactly_one_source(self) -> DayNStartRequest:
        if (self.memory_fixture_id is None) == (self.memory_bundle is None):
            raise ValueError("provide exactly one of memory_fixture_id or memory_bundle")
        return self


class MemoryBundle(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    bundle_id: str
    learner: dict[str, Any]
    events: tuple[LearnerEvent, ...]
    snapshot: dict[str, Any] | None = None
    snapshot_checksum: str | None = None


DayNStartRequest.model_rebuild()


class LearnerResponse(StrictModel):
    kind: Literal["choice", "numeric", "text"]
    value: str | float


class TurnRequest(StrictModel):
    client_turn_id: str = Field(min_length=1, max_length=120)
    activity_id: str
    response: LearnerResponse
    confidence: float | None = Field(default=None, ge=0, le=1)
    elapsed_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    requested_hint_ids: tuple[str, ...] = ()


class MemoryWrite(StrictModel):
    event_id: str | None = None
    state_version: int


class TurnResponse(StrictModel):
    turn_id: str
    outcome: Outcome
    feedback: tuple[dict[str, str], ...]
    next_activity: Activity | None = None
    placement: Placement | None = None
    why: str | None = None
    memory: MemoryWrite
    trace_id: str


class SessionStartResponse(StrictModel):
    session_id: str
    mode: Literal["day0", "dayn"]
    diagnostic_stage: str | None = None
    next_activity: Activity | None = None
    learner_summary: dict[str, Any] | None = None
    state: LearnerState | None = None
    decision: PolicyDecision | None = None
    plan: LessonPlan | None = None
    outcome: Outcome = Outcome.CONTINUE
    why: str | None = None
    trace_id: str


class CompareRequest(StrictModel):
    left_learner_id: str
    right_learner_id: str
    topic_id: str = "newton_second_law"
    objective_id: str = "apply_f_equals_ma"
    dry_run: Literal[True] = True


class EvaluationRequest(StrictModel):
    repeat_runs: int = Field(default=20, ge=1, le=50)

