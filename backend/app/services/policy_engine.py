from __future__ import annotations

from app.domain.models import (
    BaseMode,
    BlockedAlternative,
    Certainty,
    DecisionReason,
    LearnerState,
    PolicyDecision,
    SessionGoal,
)


def select_policy(
    state: LearnerState,
    goal: SessionGoal,
    *,
    content_available: bool = True,
    day0: bool = False,
) -> PolicyDecision:
    if not content_available:
        return PolicyDecision(
            base_mode=BaseMode.GUIDED,
            modifiers=("balanced",),
            provisional=True,
            certainty=Certainty.LOW,
            safe_refusal=True,
            refusal_reason="NO_VERIFIED_CONTENT",
            reasons=(
                DecisionReason(
                    rule_id="P_SAFE_NO_CONTENT",
                    metric="content.verified_available",
                    observed=False,
                    operator="==",
                    threshold=True,
                    selected_action="safe_refusal",
                ),
            ),
        )

    target = state.concepts.get(goal.concept_id)
    prerequisite = state.concepts.get("net_force")
    reasons: list[DecisionReason] = []
    blocked: list[BlockedAlternative] = []
    modifiers: list[str] = []

    if prerequisite and (
        prerequisite.mastery.effective_observations >= 2
        and prerequisite.mastery.mean < 0.45
    ):
        base = BaseMode.FOUNDATION
        reasons.append(
            DecisionReason(
                rule_id="P_FOUNDATION_PREREQUISITE_GAP",
                metric="prerequisites.net_force.mastery",
                observed=prerequisite.mastery.mean,
                operator="<",
                threshold=0.45,
                evidence_ids=prerequisite.mastery.evidence_ids,
                selected_action=base.value,
            )
        )
    elif target:
        support = target.scaffolding.mean_need
        challenge_checks = {
            "mastery": target.mastery.mean >= 0.80,
            "observations": target.mastery.effective_observations >= 6,
            "uncertainty": target.mastery.uncertainty_half_width <= 0.18,
            "support": support is not None and support < 0.20,
            "sessions": len(state.completed_sessions) >= 2,
            "fresh": not target.mastery.stale,
        }
        if all(challenge_checks.values()):
            base = BaseMode.CHALLENGE
            reasons.append(
                DecisionReason(
                    rule_id="P_CHALLENGE_READY",
                    metric="concept.challenge_gate",
                    observed=challenge_checks,
                    operator="all",
                    threshold=True,
                    evidence_ids=target.mastery.evidence_ids,
                    selected_action=base.value,
                )
            )
        else:
            base = BaseMode.GUIDED
            for check, passed in challenge_checks.items():
                if not passed:
                    blocked.append(
                        BlockedAlternative(
                            alternative=BaseMode.CHALLENGE.value,
                            reason_code=f"CHALLENGE_{check.upper()}_NOT_MET",
                            detail=f"Challenge gate '{check}' was not met.",
                        )
                    )
            reasons.append(
                DecisionReason(
                    rule_id="P_GUIDED_DEFAULT",
                    metric="concept.available_evidence",
                    observed=target.mastery.effective_observations,
                    operator="fallback",
                    threshold="challenge gates",
                    evidence_ids=target.mastery.evidence_ids,
                    selected_action=base.value,
                )
            )
    else:
        base = BaseMode.GUIDED
        reasons.append(
            DecisionReason(
                rule_id="P_GUIDED_INSUFFICIENT_EVIDENCE",
                metric="concept.evidence",
                observed=0,
                operator="<",
                threshold=4,
                selected_action=base.value,
            )
        )

    active_misconceptions = []
    for concept in state.concepts.values():
        active_misconceptions.extend(
            item.tag for item in concept.misconceptions if item.status in {"confirmed", "blocking"}
        )
    if active_misconceptions:
        modifiers.append(f"misconception_probe:{min(active_misconceptions)}")

    if not day0 and state.representation.active:
        modifiers.append(f"representation:{state.representation.active}")
    else:
        modifiers.append("balanced")

    if state.pace.small_chunks:
        modifiers.append("small_chunks")
    elif base == BaseMode.CHALLENGE or state.explicit_preferences.get("pace_preference") == "quick":
        modifiers.append("compact")

    calibration = state.calibration
    if (
        calibration.effective_observations >= 6
        and calibration.session_count >= 2
        and calibration.bias is not None
        and abs(calibration.bias) >= 0.20
    ):
        modifiers.append(
            "confidence_check_over" if calibration.bias > 0 else "confidence_check_under"
        )
    elif day0:
        high_confidence_errors = 0
        for concept in state.concepts.values():
            high_confidence_errors += sum(
                1 for evidence_id in concept.mastery.evidence_ids if evidence_id
            ) if concept.mastery.mean < 0.5 else 0
        if high_confidence_errors >= 2 and calibration.bias and calibration.bias >= 0.20:
            modifiers.append("confidence_check_provisional")

    provisional = bool(state.noisy_sessions) or not target or target.mastery.effective_observations < 4
    if day0:
        provisional = True
    certainty = Certainty.LOW if provisional else (
        Certainty.HIGH if len(state.completed_sessions) >= 2 else Certainty.MEDIUM
    )
    return PolicyDecision(
        base_mode=base,
        modifiers=tuple(dict.fromkeys(modifiers)),
        provisional=provisional,
        certainty=certainty,
        reasons=tuple(reasons),
        blocked_alternatives=tuple(blocked),
    )
