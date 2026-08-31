from __future__ import annotations

from app.core.canonical import content_hash
from app.domain.models import (
    BaseMode,
    ContentQuery,
    ContentRef,
    LearnerState,
    LessonBlock,
    LessonPlan,
    PlanLimits,
    PolicyDecision,
    SessionGoal,
)
from app.services.catalog import ContentCatalog

SKELETONS = {
    BaseMode.FOUNDATION: (
        "goal_preview",
        "prerequisite_check",
        "micro_explanation",
        "worked_example",
        "guided_item",
        "independent_check",
        "recap",
    ),
    BaseMode.GUIDED: (
        "short_principle",
        "worked_example",
        "guided_item",
        "fading_hint_item",
        "independent_check",
        "feedback",
    ),
    BaseMode.CHALLENGE: (
        "concise_principle",
        "transfer_problem",
        "delayed_hint",
        "error_reflection",
        "extension",
    ),
}


def _representation(decision: PolicyDecision) -> str:
    for modifier in decision.modifiers:
        if modifier.startswith("representation:"):
            return modifier.split(":", 1)[1]
    return "balanced"


def build_plan(
    state: LearnerState,
    decision: PolicyDecision,
    goal: SessionGoal,
    catalog: ContentCatalog,
    *,
    policy_version: str,
) -> LessonPlan | None:
    if decision.safe_refusal:
        return None
    kinds = list(SKELETONS[decision.base_mode])
    misconception_tags = tuple(
        modifier.split(":", 1)[1]
        for modifier in decision.modifiers
        if modifier.startswith("misconception_probe:")
    )
    if misconception_tags:
        kinds.insert(0, "misconception_probe")
    if any(modifier.startswith("confidence_check") for modifier in decision.modifiers):
        kinds.insert(1 if misconception_tags else 0, "confidence_activity")

    difficulty = {BaseMode.FOUNDATION: 1, BaseMode.GUIDED: 2, BaseMode.CHALLENGE: 4}[
        decision.base_mode
    ]
    representation = _representation(decision)
    blocks: list[LessonBlock] = []
    claim_ids: set[str] = set()
    for order, kind in enumerate(kinds, start=1):
        selection = catalog.retrieve(
            ContentQuery(
                concept_id=goal.concept_id,
                pedagogy=kind,
                exam_goal=goal.exam_goal,
                difficulty=difficulty,
                representation=representation,
                misconception_tags=misconception_tags if kind == "misconception_probe" else (),
            )
        )
        if selection.selected is None:
            return None
        item = selection.selected
        claim_ids.update(item.claim_ids)
        hint_limit = min(
            len(item.hints),
            {BaseMode.FOUNDATION: 3, BaseMode.GUIDED: 2, BaseMode.CHALLENGE: 1}[
                decision.base_mode
            ],
        )
        blocks.append(
            LessonBlock(
                order=order,
                kind=kind,
                content_ref=ContentRef(content_id=item.content_id, version=item.version),
                representation=item.representation,
                response_required=item.response_required,
                hint_limit=hint_limit,
                claim_ids=item.claim_ids,
                prompt=item.prompt,
                explanation=item.explanation,
                hints=item.hints[:hint_limit],
            )
        )

    input_payload = {
        "state_hash": state.state_hash,
        "goal": goal,
        "decision": decision,
        "policy_version": policy_version,
        "catalog_version": catalog.catalog.catalog_version,
    }
    input_hash = content_hash(input_payload)
    plan_without_hash = {
        "plan_schema_version": "1.0",
        "learner_state_version": state.state_version,
        "policy_version": policy_version,
        "catalog_version": catalog.catalog.catalog_version,
        "goal": goal,
        "decision": decision,
        "blocks": blocks,
        "limits": {
            "max_hints": {BaseMode.FOUNDATION: 3, BaseMode.GUIDED: 2, BaseMode.CHALLENGE: 1}[
                decision.base_mode
            ],
            "check_every_blocks": 1 if decision.base_mode == BaseMode.FOUNDATION else 2,
            "max_new_steps": 2 if "small_chunks" in decision.modifiers else 3,
            "max_model_calls": 0,
        },
        "allowed_claim_ids": sorted(claim_ids),
        "stop_conditions": [
            "NO_VERIFIED_CONTENT",
            "UNGRADABLE_RESPONSE",
            "UNKNOWN_CLAIM_ID",
            "SCHEMA_MISMATCH",
        ],
    }
    plan_hash = content_hash(plan_without_hash)
    return LessonPlan(
        plan_id=f"plan_{plan_hash.split(':')[1][:12]}",
        input_hash=input_hash,
        plan_hash=plan_hash,
        learner_state_version=state.state_version,
        policy_version=policy_version,
        catalog_version=catalog.catalog.catalog_version,
        goal=goal,
        decision=decision,
        blocks=tuple(blocks),
        limits=PlanLimits(**plan_without_hash["limits"]),
        allowed_claim_ids=tuple(sorted(claim_ids)),
        stop_conditions=tuple(plan_without_hash["stop_conditions"]),
    )

