import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from app.adapters.openai_renderer import OpenAIResponsesRenderer, SafeRenderer
from app.adapters.prompt_log import PromptLogStore
from app.domain.models import SessionGoal
from app.services.catalog import ContentCatalog
from app.services.planner import build_plan
from app.services.policy_engine import select_policy
from app.services.reducer import reduce_events

ROOT = Path(__file__).resolve().parents[2]
AS_OF = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def _plan(fixtures):
    fixture = fixtures["asha"]
    state = reduce_events(fixture.events, as_of=AS_OF)
    goal = SessionGoal(concept_id=fixture.default_topic_id)
    decision = select_policy(state, goal, content_available=True)
    catalog = ContentCatalog.load(ROOT / "data" / "content" / "catalog.json")
    plan = build_plan(state, decision, goal, catalog, policy_version="test")
    assert plan is not None
    return plan


def test_template_mode_records_exact_skipped_request(fixtures, tmp_path):
    plan = _plan(fixtures)
    store = PromptLogStore(tmp_path / "llm-calls.jsonl")
    renderer = SafeRenderer(
        api_key=None,
        model="gpt-5-mini",
        timeout_seconds=6,
        max_output_tokens=500,
        prompt_log=store,
    )

    result = renderer.render(plan)
    record = store.read_all()[0]
    prompt_input = json.loads(record["request"]["input"])

    assert result.adapter == "template"
    assert record["event_type"] == "llm_call_skipped"
    assert record["provider_called"] is False
    assert record["response"] is None
    assert record["skip_reason"] == "OPENAI_API_KEY_NOT_CONFIGURED"
    assert prompt_input["base_mode"] == plan.decision.base_mode
    assert [block["order"] for block in prompt_input["blocks"]] == [
        block.order for block in plan.blocks
    ]
    assert plan.learner_state_version not in prompt_input.values()


class _FakeResponses:
    def __init__(self, output_text):
        self.output_text = output_text
        self.request = None

    def create(self, **request):
        self.request = request
        return SimpleNamespace(
            id="resp_test",
            model="gpt-5-mini",
            output_text=self.output_text,
            usage={"input_tokens": 42, "output_tokens": 12},
        )


def test_live_boundary_records_validated_response(fixtures, tmp_path):
    plan = _plan(fixtures)
    output = json.dumps(
        {
            "blocks": [
                {"order": block.order, "connective_style": "concise"}
                for block in plan.blocks
            ]
        }
    )
    fake_responses = _FakeResponses(output)
    store = PromptLogStore(tmp_path / "llm-calls.jsonl")
    renderer = OpenAIResponsesRenderer(
        api_key="unused-test-value",
        model="gpt-5-mini",
        timeout_seconds=6,
        max_output_tokens=500,
        prompt_log=store,
        client=SimpleNamespace(responses=fake_responses),
    )

    result = renderer.render(plan)
    record = store.read_all()[0]

    assert result.adapter == "openai_responses"
    assert record["event_type"] == "llm_call"
    assert record["provider_called"] is True
    assert record["outcome"] == "success"
    assert record["validation_result"] == "pass"
    assert record["response"]["response_id"] == "resp_test"
    assert record["response"]["output_text"] == output
    assert fake_responses.request == record["request"]
