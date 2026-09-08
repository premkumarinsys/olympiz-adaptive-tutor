import json

import pytest

from app.api.chat_schemas import ChatMessageRequest, ChatStartRequest
from app.core.config import Settings
from app.core.errors import AppError, ConflictError
from app.services.chat_tutor import ChatTutor
from app.services.runtime import TutorRuntime


@pytest.fixture
def tutor(tmp_path):
    return ChatTutor(TutorRuntime(Settings(_env_file=None, openai_api_key=None,
                                          llm_api_key=None, runtime_dir=tmp_path)))


def start(tutor, learner="asha"):
    return tutor.start(ChatStartRequest(memory_fixture_id=learner))


def send(tutor, session, turn, **kwargs):
    return tutor.send(session["session_id"], ChatMessageRequest(client_turn_id=turn, **kwargs))


def test_fixed_class_lesson_and_different_current_support(tutor):
    asha, meera = start(tutor), start(tutor, "meera")
    assert asha["lesson"] == meera["lesson"]
    assert asha["memory"]["base_mode"] != meera["memory"]["base_mode"]
    assert not any(key.startswith("_") for key in asha)


def test_questions_preserve_memory_and_are_explicitly_offline(tutor):
    session = start(tutor)
    before = tutor.runtime._state("asha")
    result = send(tutor, session, "question", message="Why can velocity remain constant?")
    assert tutor.runtime._state("asha") == before
    assert result["trace"]["fallback_reason"] == "PROVIDER_NOT_CONFIGURED"
    assert result["messages"][-1]["content"]


def test_practice_has_no_answers_and_question_does_not_grade(tutor):
    session = start(tutor)
    result = send(tutor, session, "practice", action="practice")
    exercise = result["messages"][-1]["exercise"]
    assert "answer_key" not in json.dumps(result)
    before = tutor.runtime._state("asha")
    send(tutor, session, "ask", message="Is 5 the answer?")
    assert tutor.runtime._state("asha") == before
    assert exercise["exercise_id"]


def test_sessions_do_not_share_history_or_exercises(tutor):
    asha, meera = start(tutor), start(tutor, "meera")
    result = send(tutor, asha, "practice", action="practice")
    exercise = result["messages"][-1]["exercise"]
    assert len(tutor.get(meera["session_id"])["messages"]) == 1
    with pytest.raises(AppError):
        send(tutor, meera, "answer", action="answer", message="5", exercise_id=exercise["exercise_id"])


def test_request_retries_and_conflicting_turn_ids(tutor):
    session = start(tutor)
    first = send(tutor, session, "retry", message="Explain net force")
    assert send(tutor, session, "retry", message="Explain net force") == first
    with pytest.raises(ConflictError):
        send(tutor, session, "retry", message="Explain mass")


def test_practice_answer_writes_one_event_and_cannot_be_regraded(tutor):
    session = start(tutor)
    result = send(tutor, session, "practice", action="practice")
    exercise = result["messages"][-1]["exercise"]
    stored = tutor._load(session["session_id"])["_exercises"][exercise["exercise_id"]]
    item = tutor.runtime.catalog.get(stored["content_id"])
    before = len(tutor.runtime._state("asha").source_event_ids)
    kwargs = dict(action="answer", message=str(item.answer_key.value), exercise_id=exercise["exercise_id"])
    checked = send(tutor, session, "answer", **kwargs)
    assert checked["messages"][-1]["feedback"]["outcome"] == "correct"
    assert len(tutor.runtime._state("asha").source_event_ids) == before + 1
    assert send(tutor, session, "answer", **kwargs) == checked
    with pytest.raises(ConflictError):
        send(tutor, session, "answer-again", **kwargs)



def test_difficulty_and_scaffolding(tutor):
    a, b = start(tutor), start(tutor, "meera")
    x = send(tutor, a, "p", action="practice")["messages"][-1]["exercise"]
    y = send(tutor, b, "p", action="practice")["messages"][-1]["exercise"]
    assert x["difficulty"] < y["difficulty"]
    assert not y["hints"]
    assert send(tutor, a, "prep", action="prepare")["messages"][-1]["content"].startswith("Let's prepare one step")


def test_ungradable_retry(tutor):
    s = start(tutor)
    ex = send(tutor, s, "p", action="practice")["messages"][-1]["exercise"]
    stored = tutor._load(s["session_id"])["_exercises"][ex["exercise_id"]]
    item = tutor.runtime.catalog.get(stored["content_id"])
    count = tutor.runtime._state("asha").state_version
    bad = send(tutor, s, "bad", action="answer", message="?", exercise_id=ex["exercise_id"])
    assert bad["messages"][-1]["feedback"]["outcome"] == "ungradable"
    assert tutor.runtime._state("asha").state_version == count
    good = send(tutor, s, "good", action="answer", message=str(item.answer_key.value), exercise_id=ex["exercise_id"])
    assert good["messages"][-1]["feedback"]["exercise_id"] == ex["exercise_id"]


def test_live_context_and_fallback(tutor):
    from types import SimpleNamespace as NS
    calls = []
    def create(**kw):
        calls.append(kw)
        return NS(output_text="Here is an explanation of your question.")
    tutor.runtime.renderer.live = NS(client=NS(responses=NS(create=create)), model="test")
    tutor.runtime.renderer.provider = "openai_responses"
    s = start(tutor)
    r = send(tutor, s, "live", message="How does this relate to a lift?")
    assert r["trace"]["provider"] == "openai_responses"
    assert calls[0]["input"][-1]["content"] == "How does this relate to a lift?"
    assert "teacher-newton-second-law-v1" in calls[0]["instructions"]
    assert calls[0]["store"] is False
    def fail(**kw):
        raise TimeoutError()
    tutor.runtime.renderer.live.client.responses.create = fail
    r = send(tutor, s, "fail", message="Explain more")
    assert r["trace"]["fallback_reason"] == "PROVIDER_UNAVAILABLE"


def test_persisted_history(tutor):
    s = start(tutor)
    r = send(tutor, s, "r", action="revise")
    assert ChatTutor(tutor.runtime).get(s["session_id"])["messages"] == r["messages"]
