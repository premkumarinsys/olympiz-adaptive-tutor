"""Builds a RevisionPlan: an exercise set for now plus a spaced schedule.

Scheduling is model-free on every path — dates, intents and retention estimates come
from LearnerState and `as_of` alone. Exercise items come from ExerciseGenerator when a
provider is configured, and from verified catalog retrieval otherwise.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from app.core.canonical import content_hash
from app.domain.models import (
    BaseMode,
    ConceptState,
    ContentItem,
    ContentQuery,
    ContentRef,
    DecisionReason,
    ExerciseItem,
    ExerciseSet,
    ItemPresented,
    LearnerEvent,
    LearnerState,
    PolicyDecision,
    ResponseGraded,
    RevisionPlan,
    RevisionSlot,
    SessionGoal,
)
from app.services.catalog import ContentCatalog
from app.services.retention import (
    RETENTION_FLOOR,
    first_offset_days,
    half_life_days,
    priority_score,
    retention_estimate,
)

DIFFICULTY_BANDS: dict[BaseMode, tuple[int, int]] = {
    BaseMode.FOUNDATION: (1, 2),
    BaseMode.GUIDED: (2, 3),
    BaseMode.CHALLENGE: (3, 5),
}

HINT_LIMITS: dict[BaseMode, int] = {
    BaseMode.FOUNDATION: 3,
    BaseMode.GUIDED: 2,
    BaseMode.CHALLENGE: 1,
}

REVISION_STOP_CONDITIONS = (
    "NO_VERIFIED_CONTENT",
    "GENERATED_ITEM_INVALID",
    "UNKNOWN_CLAIM_ID",
    "SCHEMA_MISMATCH",
    "AS_OF_BEFORE_MEMORY",
)

# Ordered per base mode so the difficulty band actually reaches selection. The catalog
# holds one response-required item per pedagogy, so retrieval cannot discriminate on
# difficulty by itself — the order is what puts a challenger on transfer/extension work
# and a foundation learner on prerequisite and confidence items.
FALLBACK_PEDAGOGIES: dict[BaseMode, tuple[str, ...]] = {
    BaseMode.FOUNDATION: (
        "prerequisite_check",
        "confidence_activity",
        "guided_item",
        "independent_check",
        "fading_hint_item",
        "delayed_hint",
    ),
    BaseMode.GUIDED: (
        "independent_check",
        "guided_item",
        "fading_hint_item",
        "delayed_hint",
        "transfer_problem",
        "extension",
    ),
    BaseMode.CHALLENGE: (
        "transfer_problem",
        "extension",
        "delayed_hint",
        "fading_hint_item",
        "independent_check",
        "guided_item",
    ),
}

MINUTES_PER_ITEM = 4


def recent_content_usage(
    events: Sequence[LearnerEvent], as_of: datetime
) -> dict[str, float]:
    """Days since each content_id was last presented, for the cooldown rule.

    Presentation evidence comes from ItemPresented when it is emitted, and from
    ResponseGraded otherwise — a graded response implies the content was shown.
    """
    latest: dict[str, datetime] = {}
    for event in events:
        if isinstance(event, (ItemPresented, ResponseGraded)):
            seen = latest.get(event.content_id)
            if seen is None or event.occurred_at > seen:
                latest[event.content_id] = event.occurred_at
    return {
        content_id: max(0.0, (as_of - occurred).total_seconds() / 86400)
        for content_id, occurred in latest.items()
    }


def schedule_hash(plan: RevisionPlan) -> str:
    """Hash of the model-free half of the plan. Stable under a live provider."""
    return content_hash(
        {
            "as_of": plan.as_of,
            "horizon_days": plan.horizon_days,
            "goal": plan.goal,
            "decision": plan.decision,
            "schedule": plan.schedule,
        }
    )


def _cooldown_days(concept: ConceptState) -> float:
    return max(1.0, half_life_days(concept) / 3.0)


def _active_misconception(concept: ConceptState) -> str | None:
    tags = sorted(
        item.tag
        for item in concept.misconceptions
        if item.status in {"confirmed", "blocking"}
    )
    return tags[0] if tags else None


def _intent(concept: ConceptState, concept_id: str, goal: SessionGoal) -> str:
    if _active_misconception(concept):
        return "misconception_repair"
    if concept_id != goal.concept_id and concept.mastery.mean < 0.45:
        return "prerequisite_repair"
    if concept.mastery.mean >= 0.80 and concept.mastery.uncertainty_half_width <= 0.18:
        return "stretch"
    return "retrieval_practice"


def _slot_band(intent: str, base_band: tuple[int, int]) -> tuple[int, int]:
    low, high = base_band
    if intent == "stretch":
        return (min(high, 5), min(high + 1, 5))
    if intent in {"misconception_repair", "prerequisite_repair"}:
        return (max(1, low - 1), low)
    return base_band


def _excluded(
    catalog: ContentCatalog,
    recently_used: Mapping[str, float],
    concepts: Mapping[str, ConceptState],
) -> tuple[str, ...]:
    blocked = []
    for content_id, days in sorted(recently_used.items()):
        try:
            item = catalog.get(content_id)
        except KeyError:
            continue
        concept = concepts.get(item.concept_id)
        cooldown = _cooldown_days(concept) if concept else 3.0
        if days < cooldown:
            blocked.append(content_id)
    return tuple(sorted(blocked))


def _generator_memory(state: LearnerState, decision: PolicyDecision) -> dict[str, Any]:
    return {
        "base_mode": decision.base_mode.value,
        "misconceptions": sorted(
            {
                item.tag
                for concept in state.concepts.values()
                for item in concept.misconceptions
                if item.status in {"confirmed", "blocking"}
            }
        ),
        "concepts": {
            concept_id: {
                "stale": concept.mastery.stale,
                "mastery": round(concept.mastery.mean, 6),
            }
            for concept_id, concept in sorted(state.concepts.items())
        },
    }


def _exercise_item(
    item: ContentItem, order: int, hint_limit: int, *, derived_from: str | None
) -> ExerciseItem:
    assert item.answer_key is not None
    return ExerciseItem(
        order=order,
        content_ref=ContentRef(content_id=item.content_id, version=item.version),
        derived_from=derived_from,
        concept_id=item.concept_id,
        difficulty=item.difficulty,
        representation=item.representation,
        targets_misconception=(
            item.misconception_tags[0] if item.misconception_tags else None
        ),
        prompt=item.prompt,
        answer_key=item.answer_key,
        hints=item.hints[:hint_limit],
        hint_limit=min(hint_limit, len(item.hints)),
        claim_ids=item.claim_ids,
        checksum=item.checksum,
    )


def _catalog_item(
    catalog: ContentCatalog,
    concept_id: str,
    goal: SessionGoal,
    band: tuple[int, int],
    pedagogies: tuple[str, ...],
    misconception: str | None,
    excluded: tuple[str, ...],
    order: int,
    hint_limit: int,
) -> ExerciseItem | None:
    for pedagogy in pedagogies:
        selection = catalog.retrieve(
            ContentQuery(
                concept_id=concept_id,
                pedagogy=pedagogy,
                exam_goal=goal.exam_goal,
                difficulty=(band[0] + band[1]) // 2,
                misconception_tags=(misconception,) if misconception else (),
                excluded_content_ids=excluded,
            )
        )
        item = selection.selected
        if item is not None and item.answer_key is not None:
            return _exercise_item(item, order, hint_limit, derived_from=None)
    return None


def build_revision_plan(
    state: LearnerState,
    decision: PolicyDecision,
    goal: SessionGoal,
    catalog: ContentCatalog,
    generator,
    *,
    as_of: datetime,
    horizon_days: int,
    recently_used: Mapping[str, float],
    policy_version: str,
) -> RevisionPlan | None:
    if decision.safe_refusal or not catalog.supports(goal.concept_id):
        return None

    supported = {
        concept_id: concept
        for concept_id, concept in state.concepts.items()
        if catalog.supports(concept_id)
    }
    if not supported:
        return None

    base_band = DIFFICULTY_BANDS[decision.base_mode]
    hint_limit = HINT_LIMITS[decision.base_mode]
    small_chunks = "small_chunks" in decision.modifiers
    item_target = 2 if small_chunks else 4
    excluded = _excluded(catalog, recently_used, supported)

    ranked = sorted(
        supported.items(),
        key=lambda entry: (
            -priority_score(entry[1], recently_used.get(entry[0], 0.0)),
            entry[0],
        ),
    )

    memory = _generator_memory(state, decision)
    used_signatures: list[str] = []
    providers: set[str] = set()
    items: list[ExerciseItem] = []
    placed: list[str] = []
    probe_placed = False

    fill_order = [ranked[index % len(ranked)] for index in range(item_target)]
    for concept_id, concept in fill_order:
        order = len(items) + 1
        misconception = _active_misconception(concept)
        if misconception and not probe_placed:
            probe = _catalog_item(
                catalog, concept_id, goal, _slot_band("misconception_repair", base_band),
                ("misconception_probe",), misconception, excluded + tuple(placed),
                order, hint_limit,
            )
            if probe is not None:
                items.append(probe)
                placed.append(probe.content_ref.content_id)
                probe_placed = True
                continue

        result = generator.generate(
            memory=memory, action="revise", used_signatures=list(used_signatures)
        )
        providers.add(str(result.get("provider", "deterministic")))
        generated = result.get("item")
        if generated is not None and generated.answer_key is not None:
            used_signatures.append(str(result["signature"]))
            generated_item = _exercise_item(
                generated, order, hint_limit,
                derived_from=str(result.get("template_id")),
            )
            items.append(generated_item)
            placed.append(generated_item.content_ref.content_id)
            continue

        fallback = _catalog_item(
            catalog, concept_id, goal, base_band, FALLBACK_PEDAGOGIES[decision.base_mode],
            None, excluded + tuple(placed), order, hint_limit,
        )
        if fallback is not None:
            items.append(fallback)
            placed.append(fallback.content_ref.content_id)

    if not items:
        return None

    exercise_set = ExerciseSet(
        items=tuple(items),
        difficulty_band=base_band,
        estimated_minutes=len(items) * MINUTES_PER_ITEM,
    )

    slots: list[RevisionSlot] = []
    for concept_id, concept in sorted(supported.items()):
        offset = first_offset_days(concept, horizon_days=horizon_days)
        intent = _intent(concept, concept_id, goal)
        band = _slot_band(intent, base_band)
        estimate = retention_estimate(concept_id, concept, offset)
        feasible = any(
            item.concept_id == concept_id and band[0] <= item.difficulty <= band[1]
            for item in catalog.catalog.items
        )
        slots.append(
            RevisionSlot(
                order=0,
                offset_days=offset,
                scheduled_for=(as_of + timedelta(days=offset)).date(),
                concept_id=concept_id,
                intent=intent,
                target_item_count=2 if small_chunks else 3,
                difficulty_band=band,
                retention=estimate,
                reason=DecisionReason(
                    rule_id="revision_offset",
                    metric="projected_mastery",
                    observed=estimate.projected_at_slot,
                    operator="<",
                    threshold=RETENTION_FLOOR,
                    evidence_ids=concept.mastery.evidence_ids,
                    selected_action=f"review_on_day_{offset}",
                ),
                status="scheduled" if feasible else "unavailable",
                unavailable_reason=None if feasible else "NO_CONTENT_FOR_BAND",
            )
        )

    slots.sort(key=lambda slot: (slot.offset_days, slot.concept_id))
    schedule = tuple(
        slot.model_copy(update={"order": index})
        for index, slot in enumerate(slots, start=1)
    )

    claim_ids = sorted({claim for item in items for claim in item.claim_ids})
    provider = "+".join(sorted(providers)) if providers else "deterministic"

    input_hash = content_hash(
        {
            "state_hash": state.state_hash,
            "goal": goal,
            "decision": decision,
            "as_of": as_of,
            "horizon_days": horizon_days,
            "policy_version": policy_version,
            "catalog_version": catalog.catalog.catalog_version,
        }
    )
    plan_body = {
        "plan_schema_version": "1.0",
        "as_of": as_of,
        "horizon_days": horizon_days,
        "learner_state_version": state.state_version,
        "policy_version": policy_version,
        "catalog_version": catalog.catalog.catalog_version,
        "exercise_provider": provider,
        "goal": goal,
        "decision": decision,
        "exercise_set": exercise_set,
        "schedule": schedule,
        "allowed_claim_ids": claim_ids,
        "stop_conditions": list(REVISION_STOP_CONDITIONS),
    }
    plan_digest = content_hash(plan_body)
    return RevisionPlan(
        plan_id=f"rev_{plan_digest.split(':')[1][:12]}",
        input_hash=input_hash,
        plan_hash=plan_digest,
        schedule_hash=content_hash(
            {
                "as_of": as_of,
                "horizon_days": horizon_days,
                "goal": goal,
                "decision": decision,
                "schedule": schedule,
            }
        ),
        as_of=as_of,
        horizon_days=horizon_days,
        learner_state_version=state.state_version,
        policy_version=policy_version,
        catalog_version=catalog.catalog.catalog_version,
        exercise_provider=provider,
        goal=goal,
        decision=decision,
        exercise_set=exercise_set,
        schedule=schedule,
        allowed_claim_ids=tuple(claim_ids),
        stop_conditions=REVISION_STOP_CONDITIONS,
    )
