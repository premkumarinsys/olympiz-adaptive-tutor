from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime

from app.core.canonical import content_hash
from app.domain.models import (
    CalibrationState,
    ConceptState,
    EventSuperseded,
    InteractionSignal,
    LearnerEvent,
    LearnerPreferenceChanged,
    LearnerState,
    MasteryEstimate,
    MisconceptionState,
    PaceState,
    PersistedPolicy,
    PolicyApplied,
    RepresentationState,
    ResponseGraded,
    ScaffoldingEstimate,
    SessionCompleted,
    SessionStarted,
    SupportUsed,
)

ASSISTANCE_CREDIT = {
    SupportUsed.NONE: 1.0,
    SupportUsed.SELF_CORRECTED: 1.0,
    SupportUsed.ONE_HINT: 0.45,
    SupportUsed.TWO_HINTS: 0.25,
    SupportUsed.GUIDED_STEPS: 0.25,
    SupportUsed.WORKED_SOLUTION: 0.15,
    SupportUsed.ANSWER_REVEALED: 0.0,
}

ZERO_RELIABILITY_FLAGS = {"interrupted", "timed_out", "answer_exposed", "duplicate_retry"}
BLOCKING_MISCONCEPTIONS = {"adds_forces_as_scalars", "balanced_forces_absent"}


def _reliability(event: ResponseGraded) -> float:
    flags = set(event.quality_flags)
    if flags & ZERO_RELIABILITY_FLAGS:
        return 0.0
    if "guess" in flags or "ambiguous" in flags or event.grader_confidence < 0.8:
        return 0.25
    if event.support_used == SupportUsed.SELF_CORRECTED:
        return 0.5
    return 1.0


def _difficulty_multiplier(event: ResponseGraded, demonstration: float) -> float:
    successful = demonstration >= 0.8
    if event.difficulty_relation.value == "below_level":
        return 0.75 if successful else 1.0
    if event.difficulty_relation.value == "stretch":
        return 1.15 if successful else 0.75
    return 1.0


def _decay(occurred_at: datetime, as_of: datetime) -> float:
    event_time = occurred_at.astimezone(UTC)
    ref_time = as_of.astimezone(UTC)
    age_days = max(0.0, (ref_time - event_time).total_seconds() / 86400)
    return 2 ** (-age_days / 45)


def _active_events(events: Sequence[LearnerEvent]) -> list[LearnerEvent]:
    superseded = {
        event.superseded_event_id for event in events if isinstance(event, EventSuperseded)
    }
    active = [event for event in events if event.event_id not in superseded]
    return sorted(active, key=lambda event: (event.occurred_at, event.event_id))


def _noisy_sessions(events: Sequence[LearnerEvent]) -> set[str]:
    explicit = {
        event.session_id
        for event in events
        if isinstance(event, InteractionSignal) and event.signal_type == "disruption_reported"
    }
    explicit.update(
        event.session_id
        for event in events
        if isinstance(event, SessionCompleted) and event.noisy
    )
    attempts: dict[str, list[ResponseGraded]] = defaultdict(list)
    for event in events:
        if isinstance(event, ResponseGraded):
            attempts[event.session_id].append(event)
    for session_id, values in attempts.items():
        invalid = sum(bool(set(item.quality_flags) & ZERO_RELIABILITY_FLAGS) for item in values)
        if len(values) >= 4 and invalid * 2 >= len(values):
            explicit.add(session_id)
    return explicit


def _mastery(
    attempts: list[ResponseGraded], noisy: set[str], as_of: datetime
) -> MasteryEstimate:
    grouped: dict[str, list[tuple[ResponseGraded, float, float]]] = defaultdict(list)
    for event in attempts:
        z = event.first_attempt_score * ASSISTANCE_CREDIT[event.support_used]
        weight = _reliability(event) * _difficulty_multiplier(event, z) * _decay(
            event.occurred_at, as_of
        )
        grouped[event.session_id].append((event, z, weight))

    weighted: list[tuple[ResponseGraded, float, float]] = []
    for session_id, values in grouped.items():
        mass = sum(item[2] for item in values)
        cap = 2.0 if session_id in noisy else 6.0
        scale = min(1.0, cap / mass) if mass else 1.0
        weighted.extend((event, z, weight * scale) for event, z, weight in values)

    alpha = 1 + sum(weight * z for _, z, weight in weighted)
    beta = 1 + sum(weight * (1 - z) for _, z, weight in weighted)
    mean = alpha / (alpha + beta)
    effective = sum(weight for _, _, weight in weighted)
    half_width = 1.28 * math.sqrt(mean * (1 - mean) / (alpha + beta + 1))
    usable = [event for event, _, weight in weighted if weight > 0]
    stale = bool(usable) and all(
        (as_of - event.occurred_at).total_seconds() / 86400 > 90 for event in usable
    )
    return MasteryEstimate(
        alpha=round(alpha, 6),
        beta=round(beta, 6),
        mean=round(mean, 6),
        effective_observations=round(effective, 6),
        uncertainty_half_width=round(half_width, 6),
        stale=stale,
        evidence_ids=tuple(event.event_id for event in usable),
    )


def _support_need(event: ResponseGraded) -> float:
    if event.support_used == SupportUsed.NONE and event.first_attempt_score >= 0.8:
        return 0.0
    if event.support_used == SupportUsed.ONE_HINT and event.final_score >= 0.8:
        return 0.5
    if event.support_used in {SupportUsed.TWO_HINTS, SupportUsed.GUIDED_STEPS} and event.final_score >= 0.8:
        return 0.8
    if 0 < event.final_score < 0.8:
        return 0.9
    return 1.0


def _scaffolding(attempts: list[ResponseGraded], as_of: datetime) -> ScaffoldingEstimate:
    valid = [
        event
        for event in attempts
        if event.difficulty_relation.value == "on_level" and _reliability(event) > 0
    ][-8:]
    weights = [_reliability(event) * _decay(event.occurred_at, as_of) for event in valid]
    total = sum(weights)
    mean = None
    if len(valid) >= 3 and total:
        mean = sum(weight * _support_need(event) for event, weight in zip(valid, weights)) / total
    return ScaffoldingEstimate(
        mean_need=round(mean, 6) if mean is not None else None,
        effective_observations=round(total, 6),
        evidence_ids=tuple(event.event_id for event in valid),
    )


def _misconceptions(attempts: list[ResponseGraded]) -> tuple[MisconceptionState, ...]:
    by_tag: dict[str, list[ResponseGraded]] = defaultdict(list)
    for event in attempts:
        if _reliability(event) >= 0.8:
            for tag in event.error_tags:
                by_tag[tag].append(event)
    states: list[MisconceptionState] = []
    for tag, evidence in sorted(by_tag.items()):
        distinct_items = {event.content_id for event in evidence}
        independent = any(event.support_used == SupportUsed.NONE for event in evidence)
        confirmed = len(distinct_items) >= 2 and independent
        status = "blocking" if confirmed and tag in BLOCKING_MISCONCEPTIONS else (
            "confirmed" if confirmed else "candidate"
        )
        states.append(
            MisconceptionState(
                tag=tag,
                status=status,
                evidence_ids=tuple(event.event_id for event in evidence),
            )
        )
    return tuple(states)


def _calibration(
    attempts: list[ResponseGraded], noisy: set[str], as_of: datetime
) -> CalibrationState:
    valid = [
        event
        for event in attempts
        if event.session_id not in noisy
        and event.confidence_before_answer is not None
        and _reliability(event) > 0
    ]
    if not valid:
        return CalibrationState()
    weights = [_reliability(event) * _decay(event.occurred_at, as_of) for event in valid]
    total = sum(weights)
    bias = sum(
        weight * (float(event.confidence_before_answer) - event.first_attempt_score)
        for event, weight in zip(valid, weights)
    ) / total
    brier = sum(
        weight * (float(event.confidence_before_answer) - event.first_attempt_score) ** 2
        for event, weight in zip(valid, weights)
    ) / total
    return CalibrationState(
        bias=round(bias, 6),
        brier_error=round(brier, 6),
        effective_observations=len(valid),
        session_count=len({event.session_id for event in valid}),
    )


def _representation(events: Sequence[LearnerEvent], noisy: set[str]) -> RepresentationState:
    explicit = [
        event
        for event in events
        if isinstance(event, LearnerPreferenceChanged) and event.preference == "representation"
    ]
    if explicit:
        return RepresentationState(active=str(explicit[-1].value), source="user_selected")
    pairs = [
        event
        for event in events
        if isinstance(event, InteractionSignal)
        and event.signal_type == "representation_pair"
        and event.session_id not in noisy
        and event.representation
    ]
    if not pairs:
        return RepresentationState()
    latest_by_pair: dict[str, InteractionSignal] = {}
    for event in pairs:
        latest_by_pair[event.pair_id or event.event_id] = event
    values = list(latest_by_pair.values())
    mean = sum(event.value for event in values) / len(values)
    positive = sum(event.value > 0 for event in values)
    sessions = len({event.session_id for event in values})
    active = None
    if len(values) >= 4 and sessions >= 2 and mean >= 0.15 and positive >= 3:
        active = values[-1].representation
    return RepresentationState(
        active=active,
        mean_advantage=round(mean, 6),
        pair_count=len(values),
        positive_pairs=positive,
        session_count=sessions,
        source="inferred" if active else None,
    )


def _pace(events: Sequence[LearnerEvent], noisy: set[str]) -> PaceState:
    signals = [
        event
        for event in events
        if isinstance(event, InteractionSignal)
        and event.signal_type == "load"
        and event.session_id not in noisy
    ]
    if not signals:
        return PaceState()
    latest = signals[-4:]
    mean = sum(event.value for event in latest) / len(latest)
    sessions = len({event.session_id for event in latest})
    return PaceState(
        small_chunks=len(latest) >= 4 and sessions >= 2 and mean >= 0.45,
        mean_load=round(mean, 6),
        signal_count=len(latest),
        session_count=sessions,
    )


def reduce_events(
    events: Sequence[LearnerEvent], *, as_of: datetime | None = None
) -> LearnerState:
    if not events:
        raise ValueError("at least one learner event is required")
    now = as_of or max(event.occurred_at for event in events)
    active = _active_events(events)
    learner_ids = {event.learner_id for event in active}
    if len(learner_ids) != 1:
        raise ValueError("events must belong to one learner")
    learner_id = next(iter(learner_ids))
    noisy = _noisy_sessions(active)

    preferences: dict[str, object] = {}
    for event in active:
        if isinstance(event, SessionStarted):
            preferences.setdefault("exam_goal", event.exam_goal)
            preferences.setdefault("language", "en")
            preferences.setdefault("accessibility", [])
        elif isinstance(event, LearnerPreferenceChanged):
            preferences[event.preference] = event.value

    attempts = [event for event in active if isinstance(event, ResponseGraded)]
    by_concept: dict[str, list[ResponseGraded]] = defaultdict(list)
    for event in attempts:
        by_concept[event.concept_id].append(event)
    concepts = {
        concept_id: ConceptState(
            mastery=_mastery(values, noisy, now),
            scaffolding=_scaffolding(values, now),
            misconceptions=_misconceptions(values),
        )
        for concept_id, values in sorted(by_concept.items())
    }

    latest_policy = next(
        (event for event in reversed(active) if isinstance(event, PolicyApplied)), None
    )
    persisted = (
        PersistedPolicy(base_mode=latest_policy.base_mode, modifiers=latest_policy.modifiers)
        if latest_policy
        else None
    )
    completed = tuple(
        event.session_id for event in active if isinstance(event, SessionCompleted)
    )
    provisional = LearnerState(
        learner_id=learner_id,
        state_version=len(active),
        as_of_event_id=active[-1].event_id if active else None,
        explicit_preferences=preferences,
        concepts=concepts,
        calibration=_calibration(attempts, noisy, now),
        representation=_representation(active, noisy),
        pace=_pace(active, noisy),
        persisted_policy=persisted,
        noisy_sessions=tuple(sorted(noisy)),
        completed_sessions=completed,
        source_event_ids=tuple(event.event_id for event in active),
        state_hash="",
    )
    return provisional.model_copy(update={"state_hash": content_hash(provisional)})

