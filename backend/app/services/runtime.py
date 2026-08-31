from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import TypeAdapter

from app.adapters.openai_renderer import SafeRenderer
from app.adapters.repository import JsonRepository
from app.api.schemas import (
    CompareRequest,
    Day0StartRequest,
    DayNStartRequest,
    EvaluationRequest,
    MemoryWrite,
    SessionStartResponse,
    TurnRequest,
    TurnResponse,
)
from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.domain.models import (
    Activity,
    BaseMode,
    LearnerEvent,
    LearnerFixture,
    LearnerState,
    Outcome,
    Placement,
    ResponseGraded,
    SessionGoal,
    SessionRecord,
    SessionStarted,
    SupportUsed,
    Trace,
)
from app.services.catalog import ContentCatalog
from app.services.agent_graph import GraphExecution, TutorAgentGraph
from app.services.grader import grade_response
from app.services.planner import build_plan
from app.services.policy_engine import select_policy
from app.services.reducer import reduce_events
from app.services.safety import validate_plan

FIXTURE_AS_OF = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
DAY0_SEQUENCE = (
    "vector_anchor_01",
    "net_force_anchor_02",
    "n2l_anchor_03",
    "n2l_target_01",
    "n2l_recovery_01",
    "rep_text_01",
    "rep_diagram_01",
)
REFUSAL_TEXT = (
    "I don't have a verified explanation for that exact problem in this demo, so I "
    "won't invent one. I can review a supported prerequisite or mark the missing topic "
    "for a content reviewer."
)


class TutorRuntime:
    def __init__(self, settings: Settings, repository: JsonRepository | None = None) -> None:
        self.settings = settings
        self.catalog = ContentCatalog.load(settings.data_dir / "content" / "catalog.json")
        fixtures_data = json.loads(
            (settings.data_dir / "fixtures" / "learners.json").read_text(encoding="utf-8")
        )
        fixtures = TypeAdapter(list[LearnerFixture]).validate_python(fixtures_data)
        self.fixtures = {fixture.fixture_id: fixture for fixture in fixtures}
        self.repository = repository or JsonRepository(settings.runtime_dir)
        self.renderer = SafeRenderer(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            max_output_tokens=settings.openai_max_output_tokens,
        )
        self.graph = TutorAgentGraph(self.renderer)
        self.evaluation_graph = TutorAgentGraph(
            SafeRenderer(
                api_key=None,
                model=settings.openai_model,
                timeout_seconds=settings.openai_timeout_seconds,
                max_output_tokens=settings.openai_max_output_tokens,
            )
        )

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:16]}"

    @staticmethod
    def _hashed_learner(learner_id: str) -> str:
        return hashlib.sha256(learner_id.encode("utf-8")).hexdigest()[:16]

    def _activity(self, content_id: str, index: int) -> Activity:
        item = self.catalog.get(content_id)
        kind = item.answer_key.kind if item.answer_key else "content"
        return Activity(
            activity_id=f"act_{index + 1}_{content_id}",
            kind=kind,
            content_id=content_id,
            prompt=item.prompt,
            response_required=item.response_required,
            hints=item.hints,
            diagram_spec_id=item.diagram_spec_id,
        )

    def _state(self, learner_id: str, *, as_of: datetime | None = None) -> LearnerState:
        events = self.repository.load_events(learner_id)
        if not events:
            raise NotFoundError("LEARNER_MEMORY_NOT_FOUND", "No learner memory is available.")
        return reduce_events(events, as_of=as_of or max(event.occurred_at for event in events))

    def _trace(
        self,
        session: SessionRecord,
        state: LearnerState,
        *,
        turn_id: str | None,
        decision=None,
        plan=None,
        outcome: str = "pass",
        fallback_reason: str | None = None,
        pipeline: tuple[str, ...] = ("state", "safety", "policy", "retrieval", "plan", "validation"),
        elapsed_ms: float = 0,
        graph_result: GraphExecution | None = None,
    ) -> Trace:
        trace = Trace(
            trace_id=self._id("tr"),
            session_id=session.session_id,
            hashed_learner_id=self._hashed_learner(session.learner_id),
            turn_id=turn_id,
            state_version=state.state_version,
            state_hash=state.state_hash,
            policy_version=self.settings.policy_version,
            catalog_version=self.catalog.catalog.catalog_version,
            renderer_version=(
                graph_result.rendered.renderer_version
                if graph_result and graph_result.rendered
                else self.settings.renderer_version
            ),
            grader_version=self.settings.grader_version,
            input_hash=plan.input_hash if plan else None,
            plan_hash=plan.plan_hash if plan else None,
            pipeline=(
                tuple(step.node for step in graph_result.steps)
                if graph_result
                else pipeline
            ),
            evidence_used=state.source_event_ids,
            evidence_ignored=tuple(
                event_id
                for event_id in state.source_event_ids
                if any(noisy in event_id for noisy in state.noisy_sessions)
            ),
            rules=decision.reasons if decision else (),
            blocked_alternatives=decision.blocked_alternatives if decision else (),
            content_ids=tuple(block.content_ref.content_id for block in plan.blocks) if plan else (),
            validation_result=(
                "pass" if graph_result and graph_result.validation_ok else outcome
            ),
            fallback_reason=(
                graph_result.fallback_reason if graph_result else fallback_reason
            ),
            renderer_adapter=(
                graph_result.renderer_adapter if graph_result else "template"
            ),
            model_calls=graph_result.model_calls if graph_result else 0,
            graph_steps=tuple(
                step.model_dump(mode="json") for step in graph_result.steps
            ) if graph_result else (),
            timings_ms={"total": round(elapsed_ms, 3)},
        )
        self.repository.save_trace(trace)
        return trace

    def list_learners(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture_id": fixture.fixture_id,
                "display_name": fixture.display_name,
                "scenario": fixture.scenario,
                "default_topic_id": fixture.default_topic_id,
                "expected_base_mode": fixture.expected_base_mode,
                "expected_modifiers": fixture.expected_modifiers,
            }
            for fixture in self.fixtures.values()
        ]

    def start_day0(self, request: Day0StartRequest) -> SessionStartResponse:
        started = perf_counter()
        existing = self.repository.load_events(request.learner_id)
        for event in existing:
            if event.idempotency_key == request.idempotency_key and isinstance(event, SessionStarted):
                try:
                    session = self.repository.load_session(event.session_id)
                    events = self.repository.load_events(request.learner_id)
                    graph_result = self.graph.run(
                        operation="day0_start",
                        events=events,
                        as_of=max(item.occurred_at for item in events),
                        goal=None,
                        catalog=self.catalog,
                        policy_version=self.settings.policy_version,
                        day0=True,
                        state_only=True,
                    )
                    state = graph_result.learner_state
                    trace = self._trace(
                        session, state, turn_id=None, graph_result=graph_result
                    )
                    return SessionStartResponse(
                        session_id=session.session_id,
                        mode="day0",
                        diagnostic_stage="prerequisite_probe",
                        next_activity=self._activity(session.content_sequence[session.current_index], session.current_index),
                        state=state,
                        trace_id=trace.trace_id,
                    )
                except NotFoundError:
                    break
        session_id = self._id("ses")
        now = datetime.now(UTC)
        event = SessionStarted(
            event_id=self._id("evt"),
            learner_id=request.learner_id,
            session_id=session_id,
            occurred_at=now,
            idempotency_key=request.idempotency_key,
            mode="day0",
            topic_id=request.topic_id,
            exam_goal=request.exam_goal,
        )
        self.repository.append_event(event)
        session = SessionRecord(
            session_id=session_id,
            learner_id=request.learner_id,
            mode="day0",
            topic_id=request.topic_id,
            exam_goal=request.exam_goal,
            locale=request.language,
            content_sequence=DAY0_SEQUENCE,
        )
        self.repository.save_session(session)
        graph_result = self.graph.run(
            operation="day0_start",
            events=self.repository.load_events(request.learner_id),
            as_of=now,
            goal=None,
            catalog=self.catalog,
            policy_version=self.settings.policy_version,
            day0=True,
            state_only=True,
        )
        state = graph_result.learner_state
        trace = self._trace(
            session,
            state,
            turn_id=None,
            elapsed_ms=(perf_counter() - started) * 1000,
            graph_result=graph_result,
        )
        return SessionStartResponse(
            session_id=session_id,
            mode="day0",
            diagnostic_stage="prerequisite_probe",
            next_activity=self._activity(DAY0_SEQUENCE[0], 0),
            state=state,
            trace_id=trace.trace_id,
        )

    def _load_fixture_events(self, fixture_id: str) -> tuple[LearnerFixture, list[LearnerEvent]]:
        fixture = self.fixtures.get(fixture_id)
        if fixture is None:
            raise NotFoundError("PROFILE_NOT_FOUND", "The requested mock learner does not exist.")
        for event in fixture.events:
            self.repository.append_event(event)
        return fixture, list(fixture.events)

    def start_dayn(self, request: DayNStartRequest) -> SessionStartResponse:
        started = perf_counter()
        if request.memory_fixture_id:
            fixture, events = self._load_fixture_events(request.memory_fixture_id)
            topic_id = request.topic_id or fixture.default_topic_id
            learner_id = fixture.fixture_id
            summary = {
                "display_name": fixture.display_name,
                "scenario": fixture.scenario,
                "default_topic_id": fixture.default_topic_id,
            }
            as_of = FIXTURE_AS_OF
        else:
            assert request.memory_bundle is not None
            events = list(request.memory_bundle.events)
            if not events:
                raise AppError("EMPTY_MEMORY", "The supplied memory contains no events.", status_code=422)
            learner_id = events[0].learner_id
            if {event.learner_id for event in events} != {learner_id}:
                raise AppError("MEMORY_LEARNER_MISMATCH", "Memory events mix learner IDs.", status_code=422)
            for event in events:
                self.repository.append_event(event)
            topic_id = request.topic_id or "newton_second_law"
            summary = {"display_name": learner_id, "scenario": "Imported memory bundle"}
            as_of = max(event.occurred_at for event in events)

        state = reduce_events(events, as_of=as_of)
        exam_goal = str(state.explicit_preferences.get("exam_goal", "JEE Main"))
        goal = SessionGoal(concept_id=topic_id, exam_goal=exam_goal)
        graph_result = self.graph.run(
            operation="dayn_start",
            events=events,
            as_of=as_of,
            goal=goal,
            catalog=self.catalog,
            policy_version=self.settings.policy_version,
        )
        state = graph_result.learner_state
        decision = graph_result.decision
        plan = graph_result.plan
        reason = graph_result.error_code or graph_result.fallback_reason

        sequence = tuple(
            block.content_ref.content_id for block in plan.blocks if block.response_required
        ) if plan else ()
        session = SessionRecord(
            session_id=self._id("ses"),
            learner_id=learner_id,
            mode="dayn",
            topic_id=topic_id,
            exam_goal=exam_goal,
            content_sequence=sequence,
            status="refused" if plan is None else "lesson",
            locked_policy=decision,
            plan=plan,
        )
        self.repository.save_session(session)
        trace = self._trace(
            session,
            state,
            turn_id=None,
            decision=decision,
            plan=plan,
            outcome="safe_refusal" if plan is None else "pass",
            fallback_reason=reason if plan is None else None,
            elapsed_ms=(perf_counter() - started) * 1000,
            graph_result=graph_result,
        )
        return SessionStartResponse(
            session_id=session.session_id,
            mode="dayn",
            next_activity=self._activity(sequence[0], 0) if sequence else None,
            learner_summary=summary,
            state=state,
            decision=decision,
            plan=plan,
            outcome=Outcome.SAFE_REFUSAL if plan is None else Outcome.LESSON_READY,
            why=REFUSAL_TEXT if plan is None else self.student_why(decision),
            trace_id=trace.trace_id,
        )

    @staticmethod
    def student_why(decision) -> str:
        labels = {
            BaseMode.FOUNDATION: "smaller prerequisite-first steps",
            BaseMode.GUIDED: "guided problem solving with fading support",
            BaseMode.CHALLENGE: "compact independent challenges",
        }
        uncertainty = (
            "This is an early estimate."
            if decision.provisional
            else "The strategy is supported by evidence across recent sessions."
        )
        return (
            f"I am using {labels[decision.base_mode]} because of your recent practice evidence. "
            f"{uncertainty} You can change the format at any time."
        )

    def submit_turn(self, session_id: str, request: TurnRequest) -> TurnResponse:
        prior = self.repository.load_turn_result(session_id, request.client_turn_id, request)
        if prior:
            return TurnResponse.model_validate(prior)
        started = perf_counter()
        session = self.repository.load_session(session_id)
        if session.status in {"refused", "completed"}:
            raise AppError("SESSION_NOT_ACTIVE", "This session cannot accept another turn.", status_code=409)
        if session.current_index >= len(session.content_sequence):
            raise AppError("NO_ACTIVE_ACTIVITY", "The session has no active activity.", status_code=409)
        expected = self._activity(
            session.content_sequence[session.current_index], session.current_index
        )
        if request.activity_id != expected.activity_id:
            raise AppError("ACTIVITY_MISMATCH", "Submit the currently active activity.", status_code=409)
        item = self.catalog.get(expected.content_id)
        grade = grade_response(item, request.response.value)
        state_before = self._state(session.learner_id)
        turn_id = self._id("turn")

        if grade.outcome == "ungradable":
            trace = self._trace(
                session,
                state_before,
                turn_id=turn_id,
                outcome="clarification_required",
                fallback_reason="UNGRADABLE_RESPONSE",
                pipeline=("state", "grade", "clarification"),
                elapsed_ms=(perf_counter() - started) * 1000,
            )
            response = TurnResponse(
                turn_id=turn_id,
                outcome=Outcome.CLARIFICATION_REQUIRED,
                feedback=({"kind": "feedback", "text": "Please enter a numeric value or choose one listed answer."},),
                next_activity=expected,
                memory=MemoryWrite(state_version=state_before.state_version),
                trace_id=trace.trace_id,
            )
            self.repository.save_turn_result(session_id, request.client_turn_id, request, response)
            return response

        support = SupportUsed.NONE
        if len(request.requested_hint_ids) == 1:
            support = SupportUsed.ONE_HINT
        elif len(request.requested_hint_ids) >= 2:
            support = SupportUsed.TWO_HINTS
        now = datetime.now(UTC)
        event = ResponseGraded(
            event_id=self._id("evt"),
            learner_id=session.learner_id,
            session_id=session.session_id,
            occurred_at=now,
            idempotency_key=f"{session.learner_id}|{session.session_id}|{request.client_turn_id}",
            turn_id=turn_id,
            concept_id=item.concept_id,
            content_id=item.content_id,
            content_version=item.version,
            first_attempt_score=grade.score,
            final_score=grade.score,
            confidence_before_answer=request.confidence,
            support_used=support,
            error_tags=grade.error_tags,
            grader_confidence=grade.grader_confidence,
            representation=item.representation,
            support_fraction=min(1.0, len(request.requested_hint_ids) / 2),
        )
        stored, _ = self.repository.append_event(event)
        next_index = session.current_index + 1
        build_lesson = session.mode == "day0" and next_index >= len(session.content_sequence)
        graph_result = self.graph.run(
            operation="day0_turn" if session.mode == "day0" else "dayn_turn",
            events=self.repository.load_events(session.learner_id),
            as_of=now,
            goal=(
                SessionGoal(concept_id=session.topic_id, exam_goal=session.exam_goal)
                if build_lesson
                else None
            ),
            catalog=self.catalog,
            policy_version=self.settings.policy_version,
            day0=session.mode == "day0",
            state_only=not build_lesson,
            locked_decision=session.locked_policy if session.mode == "dayn" else None,
        )
        state = graph_result.learner_state
        placement = None
        next_activity = None
        decision = session.locked_policy
        plan = session.plan

        if next_index < len(session.content_sequence):
            next_activity = self._activity(session.content_sequence[next_index], next_index)
            outcome = Outcome.CONTINUE
            updated = session.model_copy(
                update={
                    "current_index": next_index,
                    "used_content_ids": session.used_content_ids + (item.content_id,),
                    "state_version": state.state_version,
                }
            )
        elif session.mode == "day0":
            decision = graph_result.decision
            plan = graph_result.plan
            placement = Placement(
                selected_strategy=decision.base_mode,
                modifiers=decision.modifiers,
                observed=tuple(
                    f"{reason.metric} supported the starting strategy" for reason in decision.reasons[:2]
                ),
                certainty=decision.certainty,
                next_evidence_needed="Two independent checks in a later session",
            )
            outcome = Outcome.PLACEMENT_READY
            updated = session.model_copy(
                update={
                    "current_index": next_index,
                    "used_content_ids": session.used_content_ids + (item.content_id,),
                    "state_version": state.state_version,
                    "status": "placement",
                    "locked_policy": decision,
                    "plan": plan,
                }
            )
        else:
            outcome = Outcome.COMPLETED
            updated = session.model_copy(
                update={
                    "current_index": next_index,
                    "used_content_ids": session.used_content_ids + (item.content_id,),
                    "state_version": state.state_version,
                    "status": "completed",
                }
            )
        self.repository.save_session(updated)
        trace = self._trace(
            updated,
            state,
            turn_id=turn_id,
            decision=decision,
            plan=plan,
            pipeline=("state", "grade", "memory", "policy", "plan", "validation"),
            elapsed_ms=(perf_counter() - started) * 1000,
            graph_result=graph_result,
        )
        feedback_text = "Correct." if grade.score == 1 else "Not yet. Review the approved explanation and try the next step."
        response = TurnResponse(
            turn_id=turn_id,
            outcome=outcome,
            feedback=({"kind": "feedback", "text": feedback_text},),
            next_activity=next_activity,
            placement=placement,
            why=self.student_why(decision) if decision else None,
            memory=MemoryWrite(event_id=stored.event_id, state_version=state.state_version),
            trace_id=trace.trace_id,
        )
        self.repository.save_turn_result(session_id, request.client_turn_id, request, response)
        return response

    def get_session(self, session_id: str) -> dict[str, Any]:
        session = self.repository.load_session(session_id)
        state = self._state(session.learner_id)
        return {
            "session": session,
            "state": state,
            "next_activity": self._activity(
                session.content_sequence[session.current_index], session.current_index
            ) if session.current_index < len(session.content_sequence) else None,
        }

    def _fixture_plan(self, fixture_id: str, topic_id: str, objective_id: str):
        fixture = self.fixtures.get(fixture_id)
        if not fixture:
            raise NotFoundError("PROFILE_NOT_FOUND", f"Mock learner '{fixture_id}' was not found.")
        goal = SessionGoal(concept_id=topic_id, objective_id=objective_id)
        graph_result = self.evaluation_graph.run(
            operation="dayn_start",
            events=list(fixture.events),
            as_of=FIXTURE_AS_OF,
            goal=goal,
            catalog=self.catalog,
            policy_version=self.settings.policy_version,
        )
        return (
            fixture,
            graph_result.learner_state,
            graph_result.decision,
            graph_result.plan,
        )

    def compare(self, request: CompareRequest) -> dict[str, Any]:
        left = self._fixture_plan(request.left_learner_id, request.topic_id, request.objective_id)
        right = self._fixture_plan(request.right_learner_id, request.topic_id, request.objective_id)
        left_plan, right_plan = left[3], right[3]
        if left_plan is None or right_plan is None:
            return {"outcome": "safe_refusal", "reason": "NO_VERIFIED_CONTENT"}
        left_kinds = [block.kind for block in left_plan.blocks]
        right_kinds = [block.kind for block in right_plan.blocks]
        differences = []
        if left[2].base_mode != right[2].base_mode:
            differences.append({"dimension": "base_mode", "left": left[2].base_mode, "right": right[2].base_mode})
        if left_kinds[0] != right_kinds[0]:
            differences.append({"dimension": "starting_block", "left": left_kinds[0], "right": right_kinds[0]})
        if left_plan.limits.max_hints != right_plan.limits.max_hints:
            differences.append({"dimension": "hint_limit", "left": left_plan.limits.max_hints, "right": right_plan.limits.max_hints})
        if left_kinds != right_kinds:
            differences.append({"dimension": "lesson_structure", "left": left_kinds, "right": right_kinds})
        if left_plan.limits.max_new_steps != right_plan.limits.max_new_steps:
            differences.append({"dimension": "chunk_size", "left": left_plan.limits.max_new_steps, "right": right_plan.limits.max_new_steps})
        return {
            "outcome": "success",
            "locked_inputs": {
                "topic_id": request.topic_id,
                "objective_id": request.objective_id,
                "policy_version": self.settings.policy_version,
                "catalog_version": self.catalog.catalog.catalog_version,
            },
            "left": {"fixture": left[0], "decision": left[2], "plan": left_plan},
            "right": {"fixture": right[0], "decision": right[2], "plan": right_plan},
            "differences": differences,
            "structural_difference_count": len(differences),
        }

    def evaluate(self, request: EvaluationRequest) -> dict[str, Any]:
        cases = []
        all_policy = True
        deterministic = True
        all_claims = True
        refusal_ok = True
        for fixture in self.fixtures.values():
            plans = []
            actual_modifiers: tuple[str, ...] = ()
            actual_mode = BaseMode.GUIDED
            outcome = "safe_refusal"
            for _ in range(request.repeat_runs):
                _, _, decision, plan = self._fixture_plan(
                    fixture.fixture_id, fixture.default_topic_id, "apply_f_equals_ma"
                )
                actual_mode = decision.base_mode
                actual_modifiers = decision.modifiers
                if plan:
                    plans.append(plan.plan_hash)
                    valid, _ = validate_plan(plan, self.catalog.catalog)
                    all_claims = all_claims and valid
                    outcome = "lesson_ready"
            policy_pass = actual_mode == fixture.expected_base_mode and all(
                expected in actual_modifiers for expected in fixture.expected_modifiers
            )
            all_policy = all_policy and policy_pass
            deterministic = deterministic and len(set(plans)) <= 1
            if fixture.fixture_id == "isha":
                refusal_ok = not plans
            cases.append(
                {
                    "fixture_id": fixture.fixture_id,
                    "expected_base_mode": fixture.expected_base_mode,
                    "actual_base_mode": actual_mode,
                    "expected_modifiers": fixture.expected_modifiers,
                    "actual_modifiers": actual_modifiers,
                    "outcome": outcome,
                    "policy_pass": policy_pass,
                    "plan_hashes": sorted(set(plans)),
                }
            )
        compare = self.compare(
            CompareRequest(left_learner_id="asha", right_learner_id="meera")
        )
        distinction = compare.get("structural_difference_count", 0) >= 3
        gates = {
            "verified_claims_only": all_claims,
            "unsupported_content_refuses": refusal_ok,
            "deterministic_plan_hash": deterministic,
            "golden_policies": all_policy,
            "personalization_structural": distinction,
        }
        passed = all(gates.values())
        return {
            "status": "passed" if passed else "failed",
            "hard_gates": gates,
            "quality_score": 90 if passed else None,
            "cases": cases,
            "honesty_notice": (
                "These tests measure deterministic behavior on fixed mocked cases. "
                "They do not demonstrate real student learning gains."
            ),
        }

    def reset_demo(self) -> dict[str, str]:
        # A non-destructive reset is intentionally limited to the process-neutral runtime files.
        for directory in (
            self.repository.events_dir,
            self.repository.sessions_dir,
            self.repository.results_dir,
            self.repository.traces_dir,
        ):
            for path in directory.glob("*.json*"):
                path.unlink(missing_ok=True)
        return {"status": "reset"}
