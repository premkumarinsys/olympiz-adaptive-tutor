from __future__ import annotations

from datetime import datetime
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import Field

from app.adapters.openai_renderer import RenderResult, SafeRenderer
from app.adapters.template_renderer import RenderedLesson
from app.domain.models import (
    LearnerEvent,
    LearnerState,
    LessonPlan,
    PolicyDecision,
    SessionGoal,
    StrictModel,
)
from app.services.catalog import ContentCatalog
from app.services.planner import build_plan
from app.services.policy_engine import select_policy
from app.services.reducer import reduce_events
from app.services.safety import validate_plan


class GraphStep(StrictModel):
    node: str
    outcome: str
    detail: str | None = None


class TutorGraphState(TypedDict, total=False):
    operation: Literal["day0_start", "day0_turn", "dayn_start", "dayn_turn"]
    events: list[LearnerEvent]
    as_of: datetime
    goal: SessionGoal
    catalog: ContentCatalog
    policy_version: str
    day0: bool
    state_only: bool
    locked_decision: PolicyDecision | None
    learner_state: LearnerState
    decision: PolicyDecision
    plan: LessonPlan | None
    rendered: RenderedLesson | None
    renderer_adapter: str
    model_calls: int
    fallback_reason: str | None
    fallback_attempted: bool
    validation_ok: bool
    error_code: str | None
    steps: list[GraphStep]


class GraphExecution(StrictModel):
    learner_state: LearnerState
    decision: PolicyDecision | None = None
    plan: LessonPlan | None = None
    rendered: RenderedLesson | None = None
    renderer_adapter: str = "none"
    model_calls: int = Field(default=0, ge=0, le=1)
    fallback_reason: str | None = None
    validation_ok: bool = True
    error_code: str | None = None
    steps: tuple[GraphStep, ...]


def _step(state: TutorGraphState, node: str, outcome: str, detail: str | None = None):
    return {"steps": [*state.get("steps", []), GraphStep(node=node, outcome=outcome, detail=detail)]}


class TutorAgentGraph:
    """Bounded graph: one deterministic pass and at most one template fallback."""

    def __init__(self, renderer: SafeRenderer) -> None:
        self.renderer = renderer
        builder = StateGraph(TutorGraphState)
        builder.add_node("validate_input", self._validate_input)
        builder.add_node("reduce_memory", self._reduce_memory)
        builder.add_node("select_policy", self._select_policy)
        builder.add_node("retrieve_and_plan", self._retrieve_and_plan)
        builder.add_node("render", self._render)
        builder.add_node("validate_output", self._validate_output)
        builder.add_node("template_fallback", self._template_fallback)
        builder.add_node("safe_refusal", self._safe_refusal)
        builder.add_node("finalize", self._finalize)

        builder.add_edge(START, "validate_input")
        builder.add_conditional_edges(
            "validate_input",
            lambda state: "safe_refusal" if state.get("error_code") else "reduce_memory",
        )
        builder.add_conditional_edges(
            "reduce_memory",
            lambda state: "finalize" if state.get("state_only") else "select_policy",
        )
        builder.add_conditional_edges(
            "select_policy",
            lambda state: "safe_refusal" if state["decision"].safe_refusal else "retrieve_and_plan",
        )
        builder.add_conditional_edges(
            "retrieve_and_plan",
            lambda state: "render" if state.get("plan") is not None else "safe_refusal",
        )
        builder.add_edge("render", "validate_output")
        builder.add_conditional_edges("validate_output", self._route_after_validation)
        builder.add_edge("template_fallback", "validate_output")
        builder.add_edge("safe_refusal", END)
        builder.add_edge("finalize", END)
        self.compiled = builder.compile()

    def _validate_input(self, state: TutorGraphState) -> dict:
        if not state.get("events"):
            return {"error_code": "EMPTY_MEMORY", **_step(state, "validate_input", "failed", "No events")}
        if not state.get("state_only") and (not state.get("goal") or not state.get("catalog")):
            return {"error_code": "GRAPH_INPUT_INVALID", **_step(state, "validate_input", "failed")}
        return _step(state, "validate_input", "passed")

    def _reduce_memory(self, state: TutorGraphState) -> dict:
        learner_state = reduce_events(state["events"], as_of=state["as_of"])
        return {"learner_state": learner_state, **_step(state, "reduce_memory", "passed")}

    def _select_policy(self, state: TutorGraphState) -> dict:
        locked = state.get("locked_decision")
        decision = locked or select_policy(
            state["learner_state"],
            state["goal"],
            content_available=state["catalog"].supports(state["goal"].concept_id),
            day0=state.get("day0", False),
        )
        return {"decision": decision, **_step(state, "select_policy", "passed")}

    def _retrieve_and_plan(self, state: TutorGraphState) -> dict:
        plan = build_plan(
            state["learner_state"],
            state["decision"],
            state["goal"],
            state["catalog"],
            policy_version=state["policy_version"],
        )
        return {
            "plan": plan,
            **_step(
                state,
                "retrieve_and_plan",
                "passed" if plan else "failed",
                None if plan else "NO_VERIFIED_CONTENT",
            ),
        }

    def _render(self, state: TutorGraphState) -> dict:
        result = self.renderer.render(state["plan"])
        return {
            "rendered": result.lesson,
            "renderer_adapter": result.adapter,
            "model_calls": result.model_calls,
            "fallback_reason": result.fallback_reason,
            **_step(state, "render", "fallback" if result.fallback_reason else "passed", result.fallback_reason),
        }

    @staticmethod
    def _render_matches_plan(plan: LessonPlan, rendered: RenderedLesson) -> bool:
        if rendered.plan_hash != plan.plan_hash or len(rendered.blocks) != len(plan.blocks):
            return False
        for approved, output in zip(plan.blocks, rendered.blocks):
            if approved.order != output.order or approved.kind != output.kind:
                return False
            if approved.explanation != output.explanation or approved.claim_ids != output.claim_ids:
                return False
            if not output.prompt.endswith(approved.prompt):
                return False
        return True

    def _validate_output(self, state: TutorGraphState) -> dict:
        plan_valid, reason = validate_plan(state["plan"], state["catalog"].catalog)
        render_valid = bool(state.get("rendered")) and self._render_matches_plan(
            state["plan"], state["rendered"]
        )
        valid = plan_valid and render_valid
        return {
            "validation_ok": valid,
            "error_code": None if valid else reason or "RENDER_VALIDATION_FAILED",
            **_step(state, "validate_output", "passed" if valid else "failed", reason),
        }

    @staticmethod
    def _route_after_validation(state: TutorGraphState) -> str:
        if state.get("validation_ok"):
            return "finalize"
        if not state.get("fallback_attempted"):
            return "template_fallback"
        return "safe_refusal"

    def _template_fallback(self, state: TutorGraphState) -> dict:
        rendered = self.renderer.template.render(state["plan"])
        return {
            "rendered": rendered,
            "renderer_adapter": "template",
            "fallback_attempted": True,
            "fallback_reason": state.get("fallback_reason") or state.get("error_code") or "VALIDATION_FAILURE",
            "error_code": None,
            **_step(state, "template_fallback", "passed"),
        }

    def _safe_refusal(self, state: TutorGraphState) -> dict:
        return {
            "plan": None,
            "rendered": None,
            "validation_ok": False,
            "error_code": state.get("error_code") or "NO_VERIFIED_CONTENT",
            **_step(state, "safe_refusal", "completed"),
        }

    def _finalize(self, state: TutorGraphState) -> dict:
        return _step(state, "finalize", "completed")

    def run(
        self,
        *,
        operation: Literal["day0_start", "day0_turn", "dayn_start", "dayn_turn"],
        events: list[LearnerEvent],
        as_of: datetime,
        goal: SessionGoal | None,
        catalog: ContentCatalog,
        policy_version: str,
        day0: bool = False,
        state_only: bool = False,
        locked_decision: PolicyDecision | None = None,
    ) -> GraphExecution:
        initial: TutorGraphState = {
            "operation": operation,
            "events": events,
            "as_of": as_of,
            "catalog": catalog,
            "policy_version": policy_version,
            "day0": day0,
            "state_only": state_only,
            "locked_decision": locked_decision,
            "model_calls": 0,
            "fallback_attempted": False,
            "validation_ok": True,
            "steps": [],
        }
        if goal is not None:
            initial["goal"] = goal
        output = self.compiled.invoke(initial)
        return GraphExecution(
            learner_state=output["learner_state"],
            decision=output.get("decision"),
            plan=output.get("plan"),
            rendered=output.get("rendered"),
            renderer_adapter=output.get("renderer_adapter", "none"),
            model_calls=output.get("model_calls", 0),
            fallback_reason=output.get("fallback_reason"),
            validation_ok=output.get("validation_ok", True),
            error_code=output.get("error_code"),
            steps=tuple(output.get("steps", [])),
        )
