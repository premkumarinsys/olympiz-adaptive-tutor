from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.schemas import (
    CompareRequest,
    Day0StartRequest,
    DayNStartRequest,
    EvaluationRequest,
    SessionStartResponse,
    TurnRequest,
    TurnResponse,
)
from app.services.runtime import TutorRuntime
from app.api.chat_schemas import ChatMessageRequest, ChatStartRequest
from app.services.chat_tutor import ChatTutor

router = APIRouter()


def get_runtime(request: Request) -> TutorRuntime:
    return request.app.state.runtime


Runtime = Annotated[TutorRuntime, Depends(get_runtime)]


@router.post("/api/v1/day0/sessions", response_model=SessionStartResponse)
def start_day0(payload: Day0StartRequest, runtime: Runtime):
    return runtime.start_day0(payload)


@router.post("/api/v1/dayn/sessions", response_model=SessionStartResponse)
def start_dayn(payload: DayNStartRequest, runtime: Runtime):
    return runtime.start_dayn(payload)


@router.post("/api/v1/sessions/{session_id}/turns", response_model=TurnResponse)
def submit_turn(session_id: str, payload: TurnRequest, runtime: Runtime):
    return runtime.submit_turn(session_id, payload)


@router.get("/api/v1/sessions/{session_id}")
def get_session(session_id: str, runtime: Runtime):
    return runtime.get_session(session_id)


@router.get("/api/v1/mock-learners")
def list_mock_learners(runtime: Runtime):
    return {"learners": runtime.list_learners()}


@router.post("/api/v1/compare")
def compare(payload: CompareRequest, runtime: Runtime):
    return runtime.compare(payload)


@router.post("/api/v1/evaluations")
def evaluate(payload: EvaluationRequest, runtime: Runtime):
    return runtime.evaluate(payload)


@router.get("/api/v1/traces/{trace_id}")
def get_trace(trace_id: str, runtime: Runtime):
    return runtime.repository.load_trace(trace_id)


@router.post("/api/v1/demo/reset")
def reset_demo(runtime: Runtime):
    return runtime.reset_demo()


@router.get("/health")
def health(runtime: Runtime):
    return {
        "status": "ready",
        "renderer": runtime.renderer.configured_adapter,
        "policy_version": runtime.settings.policy_version,
        "catalog_version": runtime.catalog.catalog.catalog_version,
    }



def get_chat(runtime: TutorRuntime) -> ChatTutor:
    if not hasattr(runtime, "chat_tutor"):
        runtime.chat_tutor = ChatTutor(runtime)
    return runtime.chat_tutor


@router.post("/api/v1/chat/sessions")
def start_chat(payload: ChatStartRequest, runtime: Runtime):
    return get_chat(runtime).start(payload)


@router.get("/api/v1/chat/sessions/{session_id}")
def get_chat_session(session_id: str, runtime: Runtime):
    return get_chat(runtime).get(session_id)


@router.post("/api/v1/chat/sessions/{session_id}/messages")
def send_chat_message(session_id: str, payload: ChatMessageRequest, runtime: Runtime):
    return get_chat(runtime).send(session_id, payload)
