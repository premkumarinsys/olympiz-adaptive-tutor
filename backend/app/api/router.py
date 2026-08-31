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
