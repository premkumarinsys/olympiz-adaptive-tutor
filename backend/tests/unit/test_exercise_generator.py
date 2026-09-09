import json
from types import SimpleNamespace as NS

from app.api.chat_schemas import ChatMessageRequest, ChatStartRequest
from app.core.config import Settings
from app.domain.models import BaseMode, ContentItem
from app.services.chat_tutor import ChatTutor
from app.services.exercise_generator import ExerciseGenerator
from app.services.grader import grade_response
from app.services.runtime import TutorRuntime


def memory(*, mode=BaseMode.GUIDED.value, misconceptions=()):
    return {
        "base_mode": mode,
        "misconceptions": list(misconceptions),
        "concepts": {},
    }


def provider_draft(template_id):
    return json.dumps(
        {
            "template_id": template_id,
            "object_name": "robot cart",
            "setting": "a robotics lab",
            "mass_kg": 6,
            "force_forward_n": 31,
            "force_opposing_n": 7,
            "acceleration_mps2": 3,
            "speed_mps": 8,
        }
    )


def responses_renderer(calls):
    def create(**kwargs):
        calls.append(kwargs)
        contract = json.loads(kwargs["input"])
        return NS(output_text=provider_draft(contract["required_template"]))

    return NS(
        provider="openai_responses",
        live=NS(client=NS(responses=NS(create=create)), model="test-model"),
    )


def test_llm_selects_parameters_while_backend_authors_and_solves():
    calls = []
    result = ExerciseGenerator(responses_renderer(calls)).generate(
        memory=memory(),
        action="practice",
        used_signatures=[],
    )

    item = result["item"]
    assert result["provider"] == "openai_responses"
    assert item.prompt.startswith("In a robotics lab")
    assert item.answer_key.value == 4
    assert item.answer_key.unit == "m/s^2"
    assert item.answer_key.tolerance == 0.011
    assert "answer" not in json.loads(calls[0]["input"])
    assert calls[0]["store"] is False
    assert calls[0]["text"]["format"]["strict"] is True


def test_invalid_or_unavailable_generation_has_no_item():
    renderer = NS(provider="openai_responses", live=None)
    result = ExerciseGenerator(renderer).generate(
        memory=memory(),
        action="practice",
        used_signatures=[],
    )

    assert "item" not in result
    assert result["fallback_reason"] == "EXERCISE_PROVIDER_NOT_CONFIGURED"
    assert result["nodes"][-1] == "use_verified_catalog_fallback"


def test_revision_contract_targets_stale_then_weaker_concept():
    stale_net_force = memory()
    stale_net_force["concepts"] = {
        "net_force": {"mastery": 0.9, "stale": True},
        "newton_second_law": {"mastery": 0.2, "stale": False},
    }
    stale = ExerciseGenerator._select_contract(
        {"memory": stale_net_force, "action": "revise", "nodes": []}
    )
    assert stale["template_id"] == "opposing_forces"

    weaker_newton = memory()
    weaker_newton["concepts"] = {
        "net_force": {"mastery": 0.8, "stale": False},
        "newton_second_law": {"mastery": 0.2, "stale": False},
    }
    weaker = ExerciseGenerator._select_contract(
        {"memory": weaker_newton, "action": "revise", "nodes": []}
    )
    assert weaker["template_id"] == "force_from_mass_and_acceleration"


def test_explicit_revision_target_controls_concept_and_difficulty_band():
    calls = []
    result = ExerciseGenerator(responses_renderer(calls)).generate(
        memory=memory(misconceptions=("force_required_for_motion",)),
        action="revise",
        used_signatures=[],
        target_concept_id="newton_second_law",
        target_misconception=None,
        target_difficulty_band=(3, 4),
    )

    assert result["template_id"] == "force_from_mass_and_acceleration"
    assert result["item"].concept_id == "newton_second_law"
    assert result["item"].difficulty == 3


def test_numeric_grading_rejects_a_wrong_physical_unit():
    result = ExerciseGenerator(responses_renderer([])).generate(
        memory=memory(),
        action="practice",
        used_signatures=[],
    )
    item = result["item"]
    answer = item.answer_key.value

    assert grade_response(item, str(answer)).outcome == "correct"
    assert grade_response(item, f"{answer} m/s^2").outcome == "correct"
    wrong_unit = grade_response(item, f"{answer} N")
    assert wrong_unit.outcome == "incorrect"
    assert wrong_unit.error_tags == ("unit_mismatch",)


def test_provider_values_are_bounded_before_they_become_an_exercise():
    raw = json.loads(provider_draft("opposing_forces"))
    raw.update(
        {
            "setting": "flat surface",
            "force_forward_n": 120,
            "force_opposing_n": 500,
            "speed_mps": 99,
        }
    )
    draft = ExerciseGenerator._validated_draft(
        json.dumps(raw),
        required_template="opposing_forces",
        variation_index=2,
    )

    assert draft.setting == "a warehouse"
    assert draft.force_forward_n == 151
    assert draft.force_opposing_n == 150
    assert draft.speed_mps == 30


def test_chat_grades_generated_item_without_exposing_answer(tmp_path):
    runtime = TutorRuntime(
        Settings(
            _env_file=None,
            openai_api_key=None,
            llm_api_key=None,
            runtime_dir=tmp_path,
        )
    )
    tutor = ChatTutor(runtime)
    calls = []
    renderer = responses_renderer(calls)
    runtime.renderer.provider = renderer.provider
    runtime.renderer.live = renderer.live
    session = tutor.start(ChatStartRequest(memory_fixture_id="asha"))

    practice = tutor.send(
        session["session_id"],
        ChatMessageRequest(client_turn_id="practice", action="practice"),
    )
    exercise = practice["messages"][-1]["exercise"]
    stored = tutor._load(session["session_id"])["_exercises"][exercise["exercise_id"]]
    item = ContentItem.model_validate(stored["item"])

    assert exercise["source"] == "llm_generated"
    assert "answer_key" not in json.dumps(practice)
    before = len(runtime._state("asha").source_event_ids)
    checked = tutor.send(
        session["session_id"],
        ChatMessageRequest(
            client_turn_id="answer",
            action="answer",
            message=str(item.answer_key.value),
            exercise_id=exercise["exercise_id"],
        ),
    )
    assert checked["messages"][-1]["feedback"]["outcome"] == "correct"
    assert len(runtime._state("asha").source_event_ids) == before + 1


def test_chat_uses_verified_bank_when_generation_is_unavailable(tmp_path):
    runtime = TutorRuntime(
        Settings(
            _env_file=None,
            openai_api_key=None,
            llm_api_key=None,
            runtime_dir=tmp_path,
        )
    )
    tutor = ChatTutor(runtime)
    session = tutor.start(ChatStartRequest(memory_fixture_id="asha"))
    result = tutor.send(
        session["session_id"],
        ChatMessageRequest(client_turn_id="practice", action="practice"),
    )

    exercise = result["messages"][-1]["exercise"]
    assert exercise["source"] == "verified_catalog"
    assert result["trace"]["fallback_reason"] == "EXERCISE_PROVIDER_NOT_CONFIGURED"
