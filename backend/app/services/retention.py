"""Retention maths for revision scheduling.

This module is deliberately separate from the reducer's evidence decay. The
reducer's 45-day half-life answers "how much should this old observation still
count toward a current belief". The half-life here answers "how long until this
learner is likely to have forgotten this concept". They are different quantities
and must not share a constant.
"""

from __future__ import annotations

from app.domain.models import ConceptState, RetentionEstimate

BASE_HALF_LIFE_DAYS = 7.0
RETENTION_FLOOR = 0.75
STALE_MAX_OFFSET_DAYS = 2
MIN_HALF_LIFE_DAYS = 0.25

_SEVERITY = {"blocking": 1.0, "confirmed": 0.6, "candidate": 0.2, "retired": 0.0}


def misconception_severity(concept: ConceptState) -> float:
    return max(
        (_SEVERITY[item.status] for item in concept.misconceptions),
        default=0.0,
    )


def half_life_days(concept: ConceptState) -> float:
    mastery = concept.mastery
    support_need = concept.scaffolding.mean_need or 0.0
    blocked = any(
        item.status in {"confirmed", "blocking"} for item in concept.misconceptions
    )
    factor = (
        (0.5 + 1.5 * mastery.mean)
        * (1.0 - 0.5 * support_need)
        * (0.5 if blocked else 1.0)
        * (1.0 - mastery.uncertainty_half_width)
    )
    return max(MIN_HALF_LIFE_DAYS, BASE_HALF_LIFE_DAYS * factor)


def projected_mastery(mean: float, half_life: float, t_days: float) -> float:
    return mean * 2 ** (-t_days / half_life)


def first_offset_days(
    concept: ConceptState, *, horizon_days: int, floor: float = RETENTION_FLOOR
) -> int:
    if concept.mastery.stale:
        return min(STALE_MAX_OFFSET_DAYS, horizon_days)
    half_life = half_life_days(concept)
    for day in range(1, horizon_days + 1):
        if projected_mastery(concept.mastery.mean, half_life, day) < floor:
            return day
    return horizon_days


def priority_score(concept: ConceptState, days_since_last_attempt: float) -> float:
    return round(
        0.40 * (1.0 - concept.mastery.mean)
        + 0.25 * concept.mastery.uncertainty_half_width
        + 0.25 * misconception_severity(concept)
        + 0.10 * min(days_since_last_attempt / 30.0, 1.0),
        10,
    )


def retention_estimate(
    concept_id: str,
    concept: ConceptState,
    offset_days: int,
    *,
    floor: float = RETENTION_FLOOR,
) -> RetentionEstimate:
    half_life = half_life_days(concept)
    return RetentionEstimate(
        concept_id=concept_id,
        mastery_now=round(concept.mastery.mean, 6),
        half_life_days=round(half_life, 6),
        projected_at_slot=round(
            projected_mastery(concept.mastery.mean, half_life, offset_days), 6
        ),
        floor=floor,
    )
