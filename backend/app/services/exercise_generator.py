"""Constrained LLM exercise generation with deterministic physics validation."""
from __future__ import annotations

import json
import re
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import Field, model_validator

from app.core.canonical import content_hash
from app.domain.models import AnswerKey, BaseMode, ContentItem, Hint, StrictModel


TemplateId = Literal[
    "opposing_forces",
    "constant_velocity",
    "force_from_mass_and_acceleration",
]

ALLOWED_SETTINGS = (
    "a classroom",
    "a warehouse",
    "an ice rink",
    "a train platform",
    "a robotics lab",
)


class ExerciseDraft(StrictModel):
    """Model-selected context and numbers; deliberately contains no answer field."""

    template_id: TemplateId
    object_name: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z][A-Za-z -]*$")
    setting: Literal[
        "a classroom",
        "a warehouse",
        "an ice rink",
        "a train platform",
        "a robotics lab",
    ]
    mass_kg: int = Field(ge=1, le=50)
    force_forward_n: int = Field(ge=2, le=200)
    force_opposing_n: int = Field(ge=0, le=150)
    acceleration_mps2: int = Field(ge=0, le=12)
    speed_mps: int = Field(ge=1, le=30)

    @model_validator(mode="after")
    def non_degenerate_forces(self):
        if (
            self.template_id == "opposing_forces"
            and self.force_forward_n <= self.force_opposing_n
        ):
            raise ValueError("forward force must exceed the opposing force")
        if (
            self.template_id == "force_from_mass_and_acceleration"
            and self.acceleration_mps2 < 1
        ):
            raise ValueError("acceleration must be positive for this template")
        return self


class ExerciseGenerationState(TypedDict, total=False):
    memory: dict[str, Any]
    action: str
    used_signatures: list[str]
    target_concept_id: str | None
    target_misconception: str | None
    target_difficulty_band: tuple[int, int] | None
    template_id: TemplateId
    difficulty: int
    variation_index: int
    draft: ExerciseDraft
    item: ContentItem
    signature: str
    provider: str
    model: str | None
    fallback_reason: str | None
    nodes: list[str]


class ExerciseGenerator:
    """Generate only parameters; trusted code authors and solves the exercise."""

    def __init__(self, renderer) -> None:
        self.renderer = renderer
        graph = StateGraph(ExerciseGenerationState)
        graph.add_node("select_exercise_contract", self._select_contract)
        graph.add_node("generate_exercise_parameters", self._generate_parameters)
        graph.add_node("validate_and_solve_exercise", self._validate_and_solve)
        graph.add_edge(START, "select_exercise_contract")
        graph.add_edge("select_exercise_contract", "generate_exercise_parameters")
        graph.add_edge("generate_exercise_parameters", "validate_and_solve_exercise")
        graph.add_edge("validate_and_solve_exercise", END)
        self.graph = graph.compile()

    def generate(
        self,
        *,
        memory: dict[str, Any],
        action: str,
        used_signatures: list[str],
        target_concept_id: str | None = None,
        target_misconception: str | None = None,
        target_difficulty_band: tuple[int, int] | None = None,
    ) -> ExerciseGenerationState:
        return self.graph.invoke(
            {
                "memory": memory,
                "action": action,
                "used_signatures": used_signatures,
                "target_concept_id": target_concept_id,
                "target_misconception": target_misconception,
                "target_difficulty_band": target_difficulty_band,
                "variation_index": len(used_signatures) + 1,
                "nodes": [],
            }
        )

    @staticmethod
    def _select_contract(state: ExerciseGenerationState) -> dict[str, Any]:
        memory = state["memory"]
        misconceptions = set(memory.get("misconceptions", ()))
        target = state.get("target_concept_id")
        target_misconception = state.get("target_misconception")
        if target == "net_force":
            template_id: TemplateId = (
                "constant_velocity"
                if target_misconception == "force_required_for_motion"
                else "opposing_forces"
            )
        elif target == "newton_second_law":
            template_id = (
                "opposing_forces"
                if target_misconception == "adds_forces_as_scalars"
                else "force_from_mass_and_acceleration"
            )
        elif "force_required_for_motion" in misconceptions:
            template_id: TemplateId = "constant_velocity"
        elif "adds_forces_as_scalars" in misconceptions:
            template_id = "opposing_forces"
        elif state["action"] == "revise":
            concepts = memory.get("concepts", {})
            target = min(
                ("net_force", "newton_second_law"),
                key=lambda concept_id: (
                    not concepts.get(concept_id, {}).get("stale", True),
                    concepts.get(concept_id, {}).get("mastery", 0.5),
                    concept_id,
                ),
            )
            template_id = (
                "opposing_forces"
                if target == "net_force"
                else "force_from_mass_and_acceleration"
            )
        elif memory.get("base_mode") == BaseMode.CHALLENGE.value:
            template_id = "force_from_mass_and_acceleration"
        else:
            template_id = "opposing_forces"
        difficulty = {
            BaseMode.FOUNDATION.value: 1,
            BaseMode.GUIDED.value: 2,
            BaseMode.CHALLENGE.value: 4,
        }.get(memory.get("base_mode"), 2)
        difficulty_band = state.get("target_difficulty_band")
        if difficulty_band is not None:
            low, high = difficulty_band
            difficulty = max(low, min(high, difficulty))
        return {
            "template_id": template_id,
            "difficulty": difficulty,
            "nodes": [*state["nodes"], "select_exercise_contract"],
        }

    def _generate_parameters(self, state: ExerciseGenerationState) -> dict[str, Any]:
        live = self.renderer.live
        if live is None:
            return {
                "provider": "deterministic",
                "model": None,
                "fallback_reason": "EXERCISE_PROVIDER_NOT_CONFIGURED",
                "nodes": [*state["nodes"], "exercise_provider_unavailable"],
            }

        schema = ExerciseDraft.model_json_schema()
        contract = {
            "required_template": state["template_id"],
            "target_difficulty": state["difficulty"],
            "variation_index": state["variation_index"],
            "previous_signatures": state["used_signatures"][-8:],
            "lesson_scope": [
                "signed net force",
                "F_net = ma",
                "constant velocity means zero net force",
            ],
        }
        instructions = (
            "Create fresh parameters for one school-physics exercise. "
            "Return JSON matching the schema exactly. Use required_template exactly. "
            "Do not calculate or include an answer, explanation, prompt, student identity, "
            "or unsupported physics. Choose plausible whole-number values. The backend "
            "will author the wording and calculate the answer independently."
        )
        chat_instructions = (
            instructions
            + ' Reply with one JSON object only, using exactly these keys: '
            + '{"template_id":"<required_template>","object_name":"<short physical object>",'
            + '"setting":"<one allowed setting>","mass_kg":<integer>,'
            + '"force_forward_n":<integer>,"force_opposing_n":<integer>,'
            + '"acceleration_mps2":<integer>,"speed_mps":<integer>}. '
            + 'Setting must be exactly one of "a classroom", "a warehouse", '
            + '"an ice rink", "a train platform", or "a robotics lab". '
            + "Use mass 1-50, forward force 2-200, opposing force 0-150, "
            + "acceleration 0-12, and speed 1-30. For opposing_forces, forward "
            + "force must be greater than opposing force. For "
            + "force_from_mass_and_acceleration, acceleration must be at least 1. "
            + "Do not echo the input contract."
        )
        try:
            if self.renderer.provider == "chat_completions":
                response = live.client.chat.completions.create(
                    model=live.model,
                    messages=[
                        {"role": "system", "content": chat_instructions},
                        {"role": "user", "content": json.dumps(contract)},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "olympiz_exercise_parameters",
                            "strict": True,
                            "schema": schema,
                        },
                    },
                    max_tokens=700,
                    temperature=0,
                )
                output = response.choices[0].message.content
            else:
                response = live.client.responses.create(
                    model=live.model,
                    instructions=instructions,
                    input=json.dumps(contract),
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "olympiz_exercise_parameters",
                            "strict": True,
                            "schema": schema,
                        },
                        "verbosity": "low",
                    },
                    max_output_tokens=700,
                    store=False,
                )
                output = response.output_text
            draft = self._validated_draft(
                output,
                required_template=state["template_id"],
                variation_index=state["variation_index"],
            )
            if draft.template_id != state["template_id"]:
                raise ValueError("provider changed the selected exercise template")
            return {
                "draft": draft,
                "provider": self.renderer.provider,
                "model": live.model,
                "fallback_reason": None,
                "nodes": [*state["nodes"], "generate_exercise_parameters"],
            }
        except Exception as error:
            return {
                "provider": "deterministic",
                "model": getattr(live, "model", None),
                "fallback_reason": f"EXERCISE_GENERATION_FALLBACK:{type(error).__name__}",
                "nodes": [*state["nodes"], "exercise_generation_fallback"],
            }

    @staticmethod
    def _validated_draft(
        output: str,
        *,
        required_template: TemplateId,
        variation_index: int,
    ) -> ExerciseDraft:
        raw = json.loads(output)
        if not isinstance(raw, dict) or set(raw) != set(ExerciseDraft.model_fields):
            raise ValueError("provider output did not match the parameter contract")
        if raw["template_id"] != required_template:
            raise ValueError("provider changed the selected exercise template")

        def bounded_integer(name: str, lower: int, upper: int) -> int:
            value = raw[name]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            return max(lower, min(upper, value))

        object_name = str(raw["object_name"]).strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z -]{1,29}", object_name):
            object_name = "cart"
        setting = raw["setting"]
        if setting not in ALLOWED_SETTINGS:
            setting = ALLOWED_SETTINGS[(variation_index - 1) % len(ALLOWED_SETTINGS)]
        forward = bounded_integer("force_forward_n", 2, 200)
        opposing = bounded_integer("force_opposing_n", 0, 150)
        acceleration = bounded_integer("acceleration_mps2", 0, 12)
        if required_template == "opposing_forces" and forward <= opposing:
            forward = opposing + 1
        if required_template == "force_from_mass_and_acceleration":
            acceleration = max(1, acceleration)
        return ExerciseDraft.model_validate(
            {
                **raw,
                "object_name": object_name,
                "setting": setting,
                "mass_kg": bounded_integer("mass_kg", 1, 50),
                "force_forward_n": forward,
                "force_opposing_n": opposing,
                "acceleration_mps2": acceleration,
                "speed_mps": bounded_integer("speed_mps", 1, 30),
            }
        )

    @staticmethod
    def _validate_and_solve(state: ExerciseGenerationState) -> dict[str, Any]:
        draft = state.get("draft")
        if draft is None:
            return {"nodes": [*state["nodes"], "use_verified_catalog_fallback"]}

        difficulty = state["difficulty"]
        name = draft.object_name.strip()
        setting = draft.setting
        if draft.template_id == "constant_velocity":
            concept_id = "net_force"
            answer = 0.0
            unit = "N"
            prompt = (
                f"A {name} moves at a constant {draft.speed_mps} m/s in {setting}. "
                "What is the net force on it in newtons?"
            )
            explanation = (
                "Constant velocity means zero acceleration, so F_net = ma = 0 N."
            )
            claims = ("claim_n2l_01", "claim_balanced_01")
            misconceptions = ("force_required_for_motion",)
            hints = (
                "Start by deciding whether constant velocity has any acceleration.",
                "Use F_net = ma after finding the acceleration.",
            )
        elif draft.template_id == "force_from_mass_and_acceleration":
            concept_id = "newton_second_law"
            answer = float(draft.mass_kg * draft.acceleration_mps2)
            unit = "N"
            prompt = (
                f"In {setting}, a {draft.mass_kg} kg {name} accelerates at "
                f"{draft.acceleration_mps2} m/s². What net force acts on it?"
            )
            explanation = (
                f"Use F_net = ma = {draft.mass_kg} × {draft.acceleration_mps2} "
                f"= {answer:g} N."
            )
            claims = ("claim_n2l_01",)
            misconceptions = ()
            hints = ("Multiply the mass by the acceleration.",)
        else:
            net_force = draft.force_forward_n - draft.force_opposing_n
            if state.get("target_concept_id") == "net_force" or (
                state.get("target_concept_id") is None and difficulty <= 1
            ):
                concept_id = "net_force"
                answer = float(net_force)
                unit = "N"
                prompt = (
                    f"In {setting}, a {name} has {draft.force_forward_n} N acting "
                    f"forward and {draft.force_opposing_n} N opposing it. "
                    "What is the net force magnitude?"
                )
                explanation = (
                    f"Opposing forces subtract: {draft.force_forward_n} - "
                    f"{draft.force_opposing_n} = {answer:g} N."
                )
                claims = ("claim_vector_01", "claim_net_force_01")
            else:
                concept_id = "newton_second_law"
                answer = round(net_force / draft.mass_kg, 2)
                unit = "m/s²"
                prompt = (
                    f"In {setting}, a {draft.mass_kg} kg {name} has "
                    f"{draft.force_forward_n} N acting forward and "
                    f"{draft.force_opposing_n} N opposing it. What is its "
                    "acceleration magnitude? Round to two decimal places."
                )
                explanation = (
                    f"First find F_net = {draft.force_forward_n} - "
                    f"{draft.force_opposing_n} = {net_force} N. Then "
                    f"a = F_net / m = {net_force} / {draft.mass_kg} = "
                    f"{answer:g} m/s²."
                )
                claims = ("claim_vector_01", "claim_n2l_01")
            misconceptions = ("adds_forces_as_scalars",)
            hints = (
                "Choose forward as positive and subtract the opposing force.",
                "Use the net force, not the larger applied force, in F_net = ma.",
            )

        replacements = {
            "\u00c2\u00b2": "^2",
            "\u00c3\u0097": "x",
            "\u00c3\u2014": "x",
            "\u00d7": "x",
        }
        for encoded, readable in replacements.items():
            prompt = prompt.replace(encoded, readable)
            explanation = explanation.replace(encoded, readable)
        if unit.startswith("m/s"):
            unit = "m/s^2"

        signature = content_hash(
            {
                "template_id": draft.template_id,
                "prompt": prompt,
                "answer": answer,
                "unit": unit,
            }
        )
        if signature in state["used_signatures"]:
            return {
                "provider": "deterministic",
                "fallback_reason": "EXERCISE_GENERATION_FALLBACK:DUPLICATE",
                "nodes": [*state["nodes"], "reject_duplicate_exercise"],
            }
        shown_hints = () if state["memory"].get("base_mode") == BaseMode.CHALLENGE.value else hints
        item = ContentItem(
            content_id=f"generated_{signature.split(':')[-1][:16]}",
            version="generated-1.0",
            status="draft",
            concept_id=concept_id,
            difficulty=difficulty,
            exam_targets=("JEE Main",),
            representation="balanced",
            pedagogy="generated_practice",
            prompt=prompt,
            explanation=explanation,
            response_required=True,
            answer_key=AnswerKey(
                kind="numeric",
                value=answer,
                tolerance=0.011 if unit == "m/s^2" else 0.001,
                unit=unit,
            ),
            hints=tuple(
                Hint(hint_id=f"{signature[-8:]}_{index}", text=text)
                for index, text in enumerate(shown_hints, start=1)
            ),
            misconception_tags=misconceptions,
            claim_ids=claims,
            checksum=signature,
        )
        return {
            "item": item,
            "signature": signature,
            "nodes": [*state["nodes"], "validate_and_solve_exercise"],
        }
