from datetime import UTC, datetime
from pathlib import Path

from app.domain.models import BaseMode, SessionGoal
from app.services.catalog import ContentCatalog
from app.services.planner import build_plan
from app.services.policy_engine import select_policy
from app.services.reducer import reduce_events
from app.services.safety import validate_plan

ROOT = Path(__file__).resolve().parents[2]
AS_OF = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def _decision(fixtures, fixture_id):
    state = reduce_events(fixtures[fixture_id].events, as_of=AS_OF)
    goal = SessionGoal(concept_id=fixtures[fixture_id].default_topic_id)
    return state, goal, select_policy(
        state,
        goal,
        content_available=goal.concept_id in {"vectors", "net_force", "newton_second_law"},
    )


def test_golden_policy_modes_and_modifiers(fixtures):
    for fixture in fixtures.values():
        _, _, decision = _decision(fixtures, fixture.fixture_id)
        assert decision.base_mode == fixture.expected_base_mode
        assert all(value in decision.modifiers for value in fixture.expected_modifiers)


def test_asha_and_meera_have_structurally_different_plans(fixtures):
    catalog = ContentCatalog.load(ROOT / "data" / "content" / "catalog.json")
    asha_state, asha_goal, asha_decision = _decision(fixtures, "asha")
    meera_state, meera_goal, meera_decision = _decision(fixtures, "meera")
    asha = build_plan(asha_state, asha_decision, asha_goal, catalog, policy_version="test")
    meera = build_plan(meera_state, meera_decision, meera_goal, catalog, policy_version="test")

    assert asha is not None and meera is not None
    assert asha.decision.base_mode == BaseMode.FOUNDATION
    assert meera.decision.base_mode == BaseMode.CHALLENGE
    assert asha.blocks[0].kind != meera.blocks[0].kind
    assert asha.limits.max_hints != meera.limits.max_hints
    assert [block.kind for block in asha.blocks] != [block.kind for block in meera.blocks]


def test_plan_hash_is_identical_across_twenty_runs(fixtures):
    catalog = ContentCatalog.load(ROOT / "data" / "content" / "catalog.json")
    state, goal, decision = _decision(fixtures, "meera")
    hashes = {
        build_plan(state, decision, goal, catalog, policy_version="test").plan_hash
        for _ in range(20)
    }

    assert len(hashes) == 1


def test_claim_validation_passes_for_verified_plan(fixtures):
    catalog = ContentCatalog.load(ROOT / "data" / "content" / "catalog.json")
    state, goal, decision = _decision(fixtures, "rohan")
    plan = build_plan(state, decision, goal, catalog, policy_version="test")

    assert plan is not None
    assert validate_plan(plan, catalog.catalog) == (True, None)


def test_unsupported_topic_refuses(fixtures):
    _state, _goal, decision = _decision(fixtures, "isha")

    assert decision.safe_refusal is True
    assert decision.refusal_reason == "NO_VERIFIED_CONTENT"
