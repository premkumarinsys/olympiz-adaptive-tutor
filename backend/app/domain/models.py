from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class BaseMode(StrEnum):
    FOUNDATION = "foundation_first"
    GUIDED = "guided_solver"
    CHALLENGE = "independent_challenger"


class Certainty(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Outcome(StrEnum):
    CONTINUE = "continue"
    PLACEMENT_READY = "placement_ready"
    LESSON_READY = "lesson_ready"
    CLARIFICATION_REQUIRED = "clarification_required"
    SAFE_SLOWDOWN = "safe_slowdown"
    SAFE_REFUSAL = "safe_refusal"
    COMPLETED = "completed"


class DifficultyRelation(StrEnum):
    BELOW = "below_level"
    ON = "on_level"
    STRETCH = "stretch"


class SupportUsed(StrEnum):
    NONE = "none"
    SELF_CORRECTED = "self_corrected"
    ONE_HINT = "one_hint"
    TWO_HINTS = "two_hints"
    GUIDED_STEPS = "guided_steps"
    WORKED_SOLUTION = "worked_solution"
    ANSWER_REVEALED = "answer_revealed"


class EventBase(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    event_id: str
    learner_id: str
    session_id: str
    occurred_at: datetime
    idempotency_key: str


class SessionStarted(EventBase):
    event_type: Literal["session_started"] = "session_started"
    mode: Literal["day0", "dayn"]
    topic_id: str
    exam_goal: str


class ItemPresented(EventBase):
    event_type: Literal["item_presented"] = "item_presented"
    turn_id: str
    content_id: str
    content_version: str


class ResponseGraded(EventBase):
    event_type: Literal["response_graded"] = "response_graded"
    turn_id: str
    concept_id: str
    content_id: str
    content_version: str
    difficulty_relation: DifficultyRelation = DifficultyRelation.ON
    first_attempt_score: float = Field(ge=0, le=1)
    final_score: float = Field(ge=0, le=1)
    confidence_before_answer: float | None = Field(default=None, ge=0, le=1)
    support_used: SupportUsed = SupportUsed.NONE
    error_tags: tuple[str, ...] = ()
    grader_confidence: float = Field(default=1.0, ge=0, le=1)
    quality_flags: tuple[str, ...] = ()
    pair_id: str | None = None
    representation: str = "balanced"
    support_fraction: float = Field(default=0.0, ge=0, le=1)


class HintRequested(EventBase):
    event_type: Literal["hint_requested"] = "hint_requested"
    turn_id: str
    content_id: str
    hint_id: str


class InteractionSignal(EventBase):
    event_type: Literal["interaction_signal"] = "interaction_signal"
    signal_type: Literal["load", "representation_pair", "disruption_reported"]
    value: float = Field(ge=-1, le=1)
    pair_id: str | None = None
    representation: str | None = None


class LearnerPreferenceChanged(EventBase):
    event_type: Literal["learner_preference_changed"] = "learner_preference_changed"
    preference: str
    value: str | bool | list[str]


class SafetyEvent(EventBase):
    event_type: Literal["safety_event"] = "safety_event"
    code: str
    detail: str


class PolicyApplied(EventBase):
    event_type: Literal["policy_applied"] = "policy_applied"
    base_mode: BaseMode
    modifiers: tuple[str, ...] = ()
    policy_version: str


class SessionCompleted(EventBase):
    event_type: Literal["session_completed"] = "session_completed"
    noisy: bool = False


class EventSuperseded(EventBase):
    event_type: Literal["event_superseded"] = "event_superseded"
    superseded_event_id: str
    replacement_event_id: str | None = None
    reason: str


LearnerEvent = Annotated[
    SessionStarted | ItemPresented | ResponseGraded | HintRequested | InteractionSignal | LearnerPreferenceChanged | SafetyEvent | PolicyApplied | SessionCompleted | EventSuperseded,
    Field(discriminator="event_type"),
]


class MasteryEstimate(StrictModel):
    alpha: float
    beta: float
    mean: float
    effective_observations: float
    uncertainty_half_width: float
    stale: bool = False
    evidence_ids: tuple[str, ...] = ()


class ScaffoldingEstimate(StrictModel):
    mean_need: float | None = None
    effective_observations: float = 0
    evidence_ids: tuple[str, ...] = ()


class MisconceptionState(StrictModel):
    tag: str
    status: Literal["candidate", "confirmed", "blocking", "retired"]
    evidence_ids: tuple[str, ...]


class ConceptState(StrictModel):
    mastery: MasteryEstimate
    scaffolding: ScaffoldingEstimate
    misconceptions: tuple[MisconceptionState, ...] = ()


class CalibrationState(StrictModel):
    bias: float | None = None
    brier_error: float | None = None
    effective_observations: int = 0
    session_count: int = 0


class RepresentationState(StrictModel):
    active: str | None = None
    mean_advantage: float | None = None
    pair_count: int = 0
    positive_pairs: int = 0
    session_count: int = 0
    source: Literal["inferred", "user_selected"] | None = None


class PaceState(StrictModel):
    small_chunks: bool = False
    mean_load: float | None = None
    signal_count: int = 0
    session_count: int = 0


class PersistedPolicy(StrictModel):
    base_mode: BaseMode
    modifiers: tuple[str, ...] = ()


class LearnerState(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    learner_id: str
    state_version: int = 0
    as_of_event_id: str | None = None
    explicit_preferences: dict[str, Any] = Field(default_factory=dict)
    concepts: dict[str, ConceptState] = Field(default_factory=dict)
    calibration: CalibrationState = Field(default_factory=CalibrationState)
    representation: RepresentationState = Field(default_factory=RepresentationState)
    pace: PaceState = Field(default_factory=PaceState)
    persisted_policy: PersistedPolicy | None = None
    noisy_sessions: tuple[str, ...] = ()
    completed_sessions: tuple[str, ...] = ()
    source_event_ids: tuple[str, ...] = ()
    state_hash: str = ""


class SessionGoal(StrictModel):
    concept_id: str
    objective_id: str = "apply_f_equals_ma"
    exam_goal: str = "JEE Main"


class DecisionReason(StrictModel):
    rule_id: str
    metric: str
    observed: Any
    operator: str
    threshold: Any
    evidence_ids: tuple[str, ...] = ()
    selected_action: str


class BlockedAlternative(StrictModel):
    alternative: str
    reason_code: str
    detail: str


class PolicyDecision(StrictModel):
    base_mode: BaseMode
    modifiers: tuple[str, ...] = ()
    provisional: bool = False
    certainty: Certainty = Certainty.LOW
    reasons: tuple[DecisionReason, ...] = ()
    blocked_alternatives: tuple[BlockedAlternative, ...] = ()
    safe_refusal: bool = False
    refusal_reason: str | None = None


class AnswerKey(StrictModel):
    kind: Literal["numeric", "choice", "text"]
    value: str | float
    tolerance: float = 0
    unit: str | None = None
    required_terms: tuple[str, ...] = ()


class Hint(StrictModel):
    hint_id: str
    text: str
    unlock_after_attempts: int = 1


class ContentItem(StrictModel):
    content_id: str
    version: str = "1.0"
    status: Literal["verified", "draft"] = "verified"
    concept_id: str
    prerequisite_ids: tuple[str, ...] = ()
    difficulty: int = Field(ge=1, le=5)
    exam_targets: tuple[str, ...] = ()
    locale: str = "en"
    representation: str = "balanced"
    pedagogy: str
    prompt: str
    explanation: str = ""
    response_required: bool = False
    answer_key: AnswerKey | None = None
    hints: tuple[Hint, ...] = ()
    misconception_tags: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()
    diagram_spec_id: str | None = None
    checksum: str

    @model_validator(mode="after")
    def answer_required_for_activity(self) -> ContentItem:
        if self.response_required and self.answer_key is None:
            raise ValueError("response-required content needs an answer key")
        return self


class Catalog(StrictModel):
    catalog_version: str
    claims: dict[str, str]
    supported_concepts: tuple[str, ...]
    items: tuple[ContentItem, ...]


class ContentQuery(StrictModel):
    concept_id: str
    pedagogy: str
    exam_goal: str
    locale: str = "en"
    difficulty: int = 2
    representation: str = "balanced"
    misconception_tags: tuple[str, ...] = ()
    excluded_content_ids: tuple[str, ...] = ()


class CandidateExclusion(StrictModel):
    content_id: str
    reason_code: str


class ContentSelection(StrictModel):
    selected: ContentItem | None
    selection_reasons: tuple[str, ...] = ()
    exclusions: tuple[CandidateExclusion, ...] = ()
    query_hash: str


class ContentRef(StrictModel):
    content_id: str
    version: str


class LessonBlock(StrictModel):
    order: int
    kind: str
    content_ref: ContentRef
    representation: str
    required: bool = True
    response_required: bool = False
    hint_limit: int = 0
    claim_ids: tuple[str, ...] = ()
    prompt: str
    explanation: str = ""
    hints: tuple[Hint, ...] = ()


class PlanLimits(StrictModel):
    max_hints: int
    check_every_blocks: int
    max_new_steps: int
    max_model_calls: int = 0


class LessonPlan(StrictModel):
    plan_schema_version: Literal["1.0"] = "1.0"
    plan_id: str
    input_hash: str
    plan_hash: str
    learner_state_version: int
    policy_version: str
    catalog_version: str
    goal: SessionGoal
    decision: PolicyDecision
    blocks: tuple[LessonBlock, ...]
    limits: PlanLimits
    allowed_claim_ids: tuple[str, ...]
    stop_conditions: tuple[str, ...]


class Activity(StrictModel):
    activity_id: str
    kind: str
    content_id: str
    prompt: str
    response_required: bool
    hints: tuple[Hint, ...] = ()
    diagram_spec_id: str | None = None


class Placement(StrictModel):
    selected_strategy: BaseMode
    modifiers: tuple[str, ...]
    observed: tuple[str, ...]
    not_inferred: tuple[str, ...] = ("intelligence", "motivation", "permanent learning style")
    certainty: Certainty
    next_evidence_needed: str


class Trace(StrictModel):
    trace_id: str
    session_id: str
    hashed_learner_id: str
    turn_id: str | None = None
    state_version: int
    state_hash: str
    policy_version: str
    catalog_version: str
    renderer_version: str
    grader_version: str
    input_hash: str | None = None
    plan_hash: str | None = None
    pipeline: tuple[str, ...]
    evidence_used: tuple[str, ...] = ()
    evidence_ignored: tuple[str, ...] = ()
    rules: tuple[DecisionReason, ...] = ()
    blocked_alternatives: tuple[BlockedAlternative, ...] = ()
    content_ids: tuple[str, ...] = ()
    validation_result: str
    fallback_reason: str | None = None
    renderer_adapter: str = "template"
    model_calls: int = Field(default=0, ge=0, le=1)
    graph_steps: tuple[dict[str, Any], ...] = ()
    state_diff: dict[str, Any] = Field(default_factory=dict)
    timings_ms: dict[str, float] = Field(default_factory=dict)


class SessionRecord(StrictModel):
    session_id: str
    learner_id: str
    mode: Literal["day0", "dayn"]
    topic_id: str
    exam_goal: str
    locale: str = "en"
    content_sequence: tuple[str, ...]
    current_index: int = 0
    used_content_ids: tuple[str, ...] = ()
    state_version: int = 0
    status: Literal["active", "placement", "lesson", "completed", "refused"] = "active"
    locked_policy: PolicyDecision | None = None
    plan: LessonPlan | None = None


class LearnerFixture(StrictModel):
    fixture_id: str
    display_name: str
    scenario: str
    default_topic_id: str
    expected_base_mode: BaseMode
    expected_modifiers: tuple[str, ...] = ()
    events: tuple[LearnerEvent, ...]
