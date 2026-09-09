from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.adapters.openai_renderer import SafeRenderer
from app.domain.models import SessionGoal
from app.services.agent_graph import TutorAgentGraph
from app.services.catalog import ContentCatalog
from app.services.exercise_generator import ExerciseGenerator

ROOT = Path(__file__).resolve().parents[2]
AS_OF = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def graph() -> TutorAgentGraph:
    return TutorAgentGraph(
        SafeRenderer(api_key=None, model="gpt-5-mini", timeout_seconds=6, max_output_tokens=500)
    )


def _run(graph, fixtures, fixture_id="kabir"):
    fixture = fixtures[fixture_id]
    return graph.run(
        operation="dayn_revision",
        events=list(fixture.events),
        as_of=AS_OF,
        goal=SessionGoal(concept_id=fixture.default_topic_id),
        catalog=ContentCatalog.load(ROOT / "data" / "content" / "catalog.json"),
        generator=ExerciseGenerator(SimpleNamespace(live=None, provider="template")),
        policy_version="test",
        horizon_days=14,
    )


def test_revision_operation_returns_a_plan(graph, fixtures):
    result = _run(graph, fixtures)
    assert result.revision_plan is not None
    assert result.plan is None


def test_revision_path_makes_no_model_calls_without_a_provider(graph, fixtures):
    result = _run(graph, fixtures)
    assert result.model_calls == 0
    assert result.renderer_adapter == "none"


def test_revision_path_skips_the_render_node(graph, fixtures):
    nodes = [step.node for step in _run(graph, fixtures).steps]
    assert "build_revision" in nodes
    assert "render" not in nodes
    assert "retrieve_and_plan" not in nodes


def test_revision_path_validates(graph, fixtures):
    assert _run(graph, fixtures).validation_ok


def test_lesson_path_still_works(graph, fixtures):
    fixture = fixtures["kabir"]
    result = graph.run(
        operation="dayn_start",
        events=list(fixture.events),
        as_of=AS_OF,
        goal=SessionGoal(concept_id=fixture.default_topic_id),
        catalog=ContentCatalog.load(ROOT / "data" / "content" / "catalog.json"),
        policy_version="test",
    )
    assert result.plan is not None
    assert result.revision_plan is None
