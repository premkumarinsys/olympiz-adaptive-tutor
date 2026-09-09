from app.domain.models import (
    ConceptState,
    MasteryEstimate,
    MisconceptionState,
    ScaffoldingEstimate,
)
from app.services.retention import (
    RETENTION_FLOOR,
    first_offset_days,
    half_life_days,
    priority_score,
    projected_mastery,
    retention_estimate,
)


def _concept(
    mean: float,
    *,
    half_width: float = 0.10,
    support: float | None = None,
    stale: bool = False,
    misconception: str | None = None,
) -> ConceptState:
    return ConceptState(
        mastery=MasteryEstimate(
            alpha=1.0,
            beta=1.0,
            mean=mean,
            effective_observations=6.0,
            uncertainty_half_width=half_width,
            stale=stale,
        ),
        scaffolding=ScaffoldingEstimate(mean_need=support),
        misconceptions=(
            (MisconceptionState(tag="t", status=misconception, evidence_ids=()),)
            if misconception
            else ()
        ),
    )


def test_stronger_mastery_yields_longer_half_life():
    assert half_life_days(_concept(0.9)) > half_life_days(_concept(0.4))


def test_confirmed_misconception_halves_the_half_life():
    plain = half_life_days(_concept(0.8))
    flagged = half_life_days(_concept(0.8, misconception="confirmed"))
    assert flagged == plain * 0.5


def test_heavy_scaffolding_shortens_the_half_life():
    assert half_life_days(_concept(0.8, support=0.8)) < half_life_days(_concept(0.8))


def test_half_life_never_collapses_to_zero():
    assert half_life_days(_concept(0.0, half_width=0.6, support=1.0, misconception="blocking")) > 0


def test_projection_decays_toward_zero():
    assert projected_mastery(0.9, 7.0, 7.0) == 0.45
    assert projected_mastery(0.9, 7.0, 0.0) == 0.9


def test_weak_concept_is_reviewed_tomorrow():
    assert first_offset_days(_concept(0.30), horizon_days=14) == 1


def test_strong_concept_earns_a_long_gap():
    assert first_offset_days(_concept(0.95, half_width=0.05), horizon_days=14) >= 7


def test_offset_is_capped_by_the_horizon():
    assert first_offset_days(_concept(0.99, half_width=0.01), horizon_days=5) == 5


def test_stale_concept_is_clamped_regardless_of_mastery():
    assert first_offset_days(_concept(0.99, half_width=0.01, stale=True), horizon_days=14) == 2


def test_offset_is_monotone_in_mastery():
    horizon = 30
    offsets = [
        first_offset_days(_concept(mean / 100), horizon_days=horizon)
        for mean in range(10, 100, 5)
    ]
    assert offsets == sorted(offsets)


def test_priority_ranks_blocking_misconception_above_a_clean_weak_concept():
    blocked = priority_score(_concept(0.60, misconception="blocking"), days_since_last_attempt=0)
    plain = priority_score(_concept(0.60), days_since_last_attempt=0)
    assert blocked > plain


def test_priority_is_higher_for_weaker_mastery():
    assert priority_score(_concept(0.2), 0) > priority_score(_concept(0.8), 0)


def test_retention_estimate_reports_the_projection_at_the_slot():
    concept = _concept(0.9, half_width=0.05)
    estimate = retention_estimate("newton_second_law", concept, 3)
    assert estimate.concept_id == "newton_second_law"
    assert estimate.floor == RETENTION_FLOOR
    assert estimate.projected_at_slot < estimate.mastery_now
