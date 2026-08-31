from datetime import UTC, datetime

from app.services.reducer import reduce_events

AS_OF = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def test_independent_success_builds_challenge_ready_state(fixtures):
    state = reduce_events(fixtures["meera"].events, as_of=AS_OF)
    target = state.concepts["newton_second_law"]

    assert target.mastery.mean >= 0.8
    assert target.mastery.effective_observations >= 6
    assert target.mastery.uncertainty_half_width <= 0.18
    assert target.scaffolding.mean_need == 0


def test_noisy_session_keeps_invalid_attempts_at_zero_weight(fixtures):
    state = reduce_events(fixtures["dev"].events, as_of=AS_OF)

    assert state.noisy_sessions == ("dev_s1",)
    assert state.concepts["newton_second_law"].mastery.effective_observations <= 2
    assert state.calibration.effective_observations == 0


def test_prerequisite_failures_are_auditable(fixtures):
    state = reduce_events(fixtures["asha"].events, as_of=AS_OF)
    prerequisite = state.concepts["net_force"]

    assert prerequisite.mastery.mean < 0.45
    assert prerequisite.mastery.effective_observations >= 1.5
    assert prerequisite.misconceptions[0].status == "blocking"


def test_representation_requires_four_pairs_across_two_sessions(fixtures):
    state = reduce_events(fixtures["zoya"].events, as_of=AS_OF)

    assert state.representation.active == "diagram_supported"
    assert state.representation.pair_count == 4
    assert state.representation.session_count == 2


def test_state_hash_is_reproducible(fixtures):
    first = reduce_events(fixtures["rohan"].events, as_of=AS_OF)
    second = reduce_events(fixtures["rohan"].events, as_of=AS_OF)

    assert first.state_hash == second.state_hash

