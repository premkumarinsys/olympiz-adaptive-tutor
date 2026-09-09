from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.models import SessionGoal
from app.services.catalog import ContentCatalog
from app.services.exercise_generator import ExerciseGenerator
from app.services.policy_engine import select_policy
from app.services.reducer import reduce_events
from app.services.revision_planner import build_revision_plan, recent_content_usage

ROOT = Path(__file__).resolve().parents[2]
AS_OF = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def catalog() -> ContentCatalog:
    return ContentCatalog.load(ROOT / "data" / "content" / "catalog.json")


@pytest.fixture(scope="module")
def generator() -> ExerciseGenerator:
    # renderer.live is None, so the generator short-circuits to catalog fallback.
    return ExerciseGenerator(SimpleNamespace(live=None, provider="template"))


def _plan(fixtures, catalog, generator, fixture_id, *, horizon_days=14, as_of=AS_OF):
    fixture = fixtures[fixture_id]
    events = list(fixture.events)
    state = reduce_events(events, as_of=as_of)
    goal = SessionGoal(concept_id=fixture.default_topic_id)
    decision = select_policy(state, goal, content_available=True)
    return build_revision_plan(
        state,
        decision,
        goal,
        catalog,
        generator,
        as_of=as_of,
        horizon_days=horizon_days,
        recently_used=recent_content_usage(events, as_of),
        policy_version="test",
    )


def test_plan_has_an_exercise_set_and_a_schedule(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "kabir")
    assert plan is not None
    assert plan.exercise_set.items
    assert plan.schedule


def test_no_provider_yields_only_verified_catalog_items(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "kabir")
    assert plan.exercise_provider == "deterministic"
    for item in plan.exercise_set.items:
        assert item.derived_from is None
        assert not item.content_ref.content_id.startswith("generated_")
        catalog.get(item.content_ref.content_id)  # raises if not a real catalog item


def test_kabir_first_slot_repairs_his_confirmed_misconception(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "kabir")
    first = plan.schedule[0]
    assert first.intent == "misconception_repair"
    assert first.offset_days <= 3


def test_meera_earns_a_long_first_gap(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "meera")
    assert plan.schedule[0].offset_days >= 7


def test_asha_gets_small_sets(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "asha")
    assert "small_chunks" in plan.decision.modifiers
    assert plan.schedule[0].target_item_count <= 2
    assert len(plan.exercise_set.items) <= 2


def test_schedule_is_ordered_by_offset_then_concept(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "rohan")
    keys = [(slot.offset_days, slot.concept_id) for slot in plan.schedule]
    assert keys == sorted(keys)
    assert [slot.order for slot in plan.schedule] == list(range(1, len(plan.schedule) + 1))


def test_scheduled_dates_match_the_offsets(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "rohan")
    for slot in plan.schedule:
        assert (slot.scheduled_for - AS_OF.date()).days == slot.offset_days


def test_no_slot_exceeds_the_horizon(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "meera", horizon_days=5)
    assert all(slot.offset_days <= 5 for slot in plan.schedule)


def test_plan_hash_is_stable_without_a_provider(fixtures, catalog, generator):
    hashes = {_plan(fixtures, catalog, generator, "kabir").plan_hash for _ in range(10)}
    assert len(hashes) == 1


def test_schedule_hash_ignores_the_exercise_set(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "kabir")
    mutated = plan.model_copy(
        update={
            "exercise_set": plan.exercise_set.model_copy(
                update={"items": plan.exercise_set.items[:1]}
            )
        }
    )
    from app.services.revision_planner import schedule_hash

    assert schedule_hash(mutated) == plan.schedule_hash


def test_plan_hash_changes_with_as_of(fixtures, catalog, generator):
    early = _plan(fixtures, catalog, generator, "kabir", as_of=AS_OF)
    later = _plan(
        fixtures, catalog, generator, "kabir",
        as_of=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
    )
    assert early.plan_hash != later.plan_hash


def test_cooldown_keeps_recently_seen_items_out_of_the_exercise_set(
    fixtures, catalog, generator
):
    fixture = fixtures["rohan"]
    events = list(fixture.events)
    state = reduce_events(events, as_of=AS_OF)
    goal = SessionGoal(concept_id=fixture.default_topic_id)
    decision = select_policy(state, goal, content_available=True)
    plan = build_revision_plan(
        state, decision, goal, catalog, generator,
        as_of=AS_OF, horizon_days=14,
        recently_used={"n2l_target_01": 0.0, "n2l_recovery_01": 0.0},
        policy_version="test",
    )
    reused = {item.content_ref.content_id for item in plan.exercise_set.items}
    assert "n2l_target_01" not in reused
    assert "n2l_recovery_01" not in reused


def test_every_exercise_claim_is_allowed_and_known(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "kabir")
    known = set(catalog.catalog.claims)
    assert set(plan.allowed_claim_ids) <= known
    for item in plan.exercise_set.items:
        assert set(item.claim_ids) <= set(plan.allowed_claim_ids)


def test_every_item_is_answerable(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "kabir")
    for item in plan.exercise_set.items:
        assert item.answer_key is not None


def test_unsupported_concept_refuses(fixtures, catalog, generator):
    fixture = fixtures["kabir"]
    state = reduce_events(list(fixture.events), as_of=AS_OF)
    goal = SessionGoal(concept_id="thermodynamics")
    decision = select_policy(state, goal, content_available=False)
    plan = build_revision_plan(
        state, decision, goal, catalog, generator,
        as_of=AS_OF, horizon_days=14, recently_used={}, policy_version="test",
    )
    assert plan is None


def test_recent_content_usage_reports_days_since_presentation(fixtures):
    usage = recent_content_usage(list(fixtures["kabir"].events), AS_OF)
    assert usage
    assert all(days >= 0 for days in usage.values())


def test_exercise_items_are_distinct(fixtures, catalog, generator):
    for fixture_id in ("rohan", "meera", "kabir", "tara", "zoya", "dev"):
        plan = _plan(fixtures, catalog, generator, fixture_id)
        ids = [item.content_ref.content_id for item in plan.exercise_set.items]
        assert len(ids) == len(set(ids)), f"{fixture_id} repeats an item: {ids}"


def test_every_learner_with_evidence_gets_a_usable_set(fixtures, catalog, generator):
    for fixture_id in ("asha", "rohan", "meera", "kabir", "tara", "zoya", "dev"):
        plan = _plan(fixtures, catalog, generator, fixture_id)
        assert plan is not None, f"{fixture_id} produced no plan"
        assert plan.exercise_set.items, f"{fixture_id} produced an empty exercise set"


from app.services.safety import validate_revision_plan


def test_valid_plan_passes_validation(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "kabir")
    ok, reason = validate_revision_plan(plan, catalog.catalog)
    assert ok
    assert reason is None


def test_unknown_claim_is_rejected(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "kabir")
    tampered = plan.model_copy(update={"allowed_claim_ids": ("claim_not_real",)})
    ok, reason = validate_revision_plan(tampered, catalog.catalog)
    assert not ok
    assert reason == "UNKNOWN_CLAIM_ID"


def test_out_of_order_slots_are_rejected(fixtures, catalog, generator):
    # asha is the only fixture with two graded concepts, so she is the only one whose
    # schedule can be put out of order. Do not swap in another fixture and skip.
    plan = _plan(fixtures, catalog, generator, "asha")
    assert len(plan.schedule) >= 2, "asha must produce a multi-slot schedule"
    shuffled = (plan.schedule[1], plan.schedule[0], *plan.schedule[2:])
    tampered = plan.model_copy(update={"schedule": shuffled})
    ok, reason = validate_revision_plan(tampered, catalog.catalog)
    assert not ok
    assert reason == "SLOT_ORDER_INVALID"


def test_slot_beyond_horizon_is_rejected(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "kabir")
    stretched = plan.schedule[0].model_copy(update={"offset_days": 99})
    tampered = plan.model_copy(update={"schedule": (stretched, *plan.schedule[1:])})
    ok, reason = validate_revision_plan(tampered, catalog.catalog)
    assert not ok
    # kabir produces exactly one slot, so the order checks pass unconditionally and
    # only the horizon check can fire. Assert it exactly.
    assert reason == "SLOT_BEYOND_HORIZON"


def test_catalog_item_that_is_not_in_the_catalog_is_rejected(
    fixtures, catalog, generator
):
    plan = _plan(fixtures, catalog, generator, "kabir")
    first = plan.exercise_set.items[0]
    ghost = first.model_copy(
        update={"content_ref": first.content_ref.model_copy(update={"content_id": "ghost_01"})}
    )
    tampered = plan.model_copy(
        update={
            "exercise_set": plan.exercise_set.model_copy(
                update={"items": (ghost, *plan.exercise_set.items[1:])}
            )
        }
    )
    ok, reason = validate_revision_plan(tampered, catalog.catalog)
    assert not ok
    assert reason == "UNKNOWN_CONTENT_ID"


def test_generated_item_must_use_a_generated_content_id(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "kabir")
    first = plan.exercise_set.items[0]
    mislabelled = first.model_copy(update={"derived_from": "opposing_forces"})
    tampered = plan.model_copy(
        update={
            "exercise_set": plan.exercise_set.model_copy(
                update={"items": (mislabelled, *plan.exercise_set.items[1:])}
            )
        }
    )
    ok, reason = validate_revision_plan(tampered, catalog.catalog)
    assert not ok
    assert reason == "GENERATED_ITEM_INVALID"


def test_empty_exercise_set_is_rejected(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "kabir")
    tampered = plan.model_copy(
        update={"exercise_set": plan.exercise_set.model_copy(update={"items": ()})}
    )
    ok, reason = validate_revision_plan(tampered, catalog.catalog)
    assert not ok
    assert reason == "NO_VERIFIED_CONTENT"


def test_empty_schedule_is_rejected(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "kabir")
    tampered = plan.model_copy(update={"schedule": ()})
    ok, reason = validate_revision_plan(tampered, catalog.catalog)
    assert not ok
    assert reason == "NO_VERIFIED_CONTENT"


def test_challenger_gets_stretch_difficulty_items(fixtures, catalog, generator):
    for fixture_id in ("meera", "tara"):
        plan = _plan(fixtures, catalog, generator, fixture_id)
        assert max(item.difficulty for item in plan.exercise_set.items) >= 4, (
            f"{fixture_id} is a challenger but got "
            f"{[item.difficulty for item in plan.exercise_set.items]}"
        )


def test_foundation_learner_is_not_given_stretch_items(fixtures, catalog, generator):
    plan = _plan(fixtures, catalog, generator, "asha")
    assert max(item.difficulty for item in plan.exercise_set.items) <= 2, (
        f"asha is foundation-first but got "
        f"{[item.difficulty for item in plan.exercise_set.items]}"
    )


def test_different_base_modes_get_different_item_sets(fixtures, catalog, generator):
    challenger = {
        item.content_ref.content_id
        for item in _plan(fixtures, catalog, generator, "meera").exercise_set.items
    }
    guided = {
        item.content_ref.content_id
        for item in _plan(fixtures, catalog, generator, "kabir").exercise_set.items
    }
    assert challenger != guided
