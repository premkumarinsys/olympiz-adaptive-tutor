from __future__ import annotations

import json
from typing import Literal

from openai import OpenAI
from pydantic import Field, model_validator

from app.adapters.template_renderer import RenderedBlock, RenderedLesson, TemplateRenderer
from app.domain.models import LessonPlan, StrictModel


class LiveBlockStyle(StrictModel):
    order: int = Field(ge=1)
    connective_style: Literal["concise", "encouraging", "reflective"]


class LiveRenderSelection(StrictModel):
    blocks: tuple[LiveBlockStyle, ...]

    @model_validator(mode="after")
    def unique_order(self) -> "LiveRenderSelection":
        orders = [block.order for block in self.blocks]
        if len(orders) != len(set(orders)):
            raise ValueError("render selection contains duplicate block orders")
        return self


class RenderResult(StrictModel):
    lesson: RenderedLesson
    adapter: Literal["template", "openai_responses"]
    model_calls: int = Field(ge=0, le=1)
    fallback_reason: str | None = None


LEAD_INS = {
    "concise": "Focus on this step.",
    "encouraging": "Take this one step at a time.",
    "reflective": "Pause and connect this step to what you already established.",
}


class OpenAIResponsesRenderer:
    """One-call style selector; verified academic content always comes from the plan."""

    version = "openai-responses-structured-1.0"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> None:
        self.client = OpenAI(api_key=api_key, timeout=timeout_seconds)
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.template = TemplateRenderer()

    def render(self, plan: LessonPlan) -> RenderResult:
        schema = LiveRenderSelection.model_json_schema()
        response = self.client.responses.create(
            model=self.model,
            instructions=(
                "Select only a connective style for each approved lesson block. "
                "Do not add or rewrite academic content, equations, numbers, hints, or answers."
            ),
            input=json.dumps(
                {
                    "base_mode": plan.decision.base_mode,
                    "modifiers": plan.decision.modifiers,
                    "blocks": [
                        {"order": block.order, "kind": block.kind}
                        for block in plan.blocks
                    ],
                },
                separators=(",", ":"),
            ),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "olympiz_render_selection",
                    "strict": True,
                    "schema": schema,
                },
                "verbosity": "low",
            },
            max_output_tokens=self.max_output_tokens,
            store=False,
        )
        selection = LiveRenderSelection.model_validate_json(response.output_text)
        expected_orders = [block.order for block in plan.blocks]
        actual_orders = [block.order for block in selection.blocks]
        if actual_orders != expected_orders:
            raise ValueError("renderer changed or omitted the approved block order")
        styles = {block.order: block.connective_style for block in selection.blocks}
        rendered = self.template.render(plan)
        styled = rendered.model_copy(
            update={
                "renderer_version": self.version,
                "blocks": tuple(
                    RenderedBlock(
                        order=block.order,
                        kind=block.kind,
                        prompt=f"{LEAD_INS[styles[block.order]]} {block.prompt}",
                        explanation=block.explanation,
                        claim_ids=block.claim_ids,
                    )
                    for block in rendered.blocks
                ),
            }
        )
        return RenderResult(lesson=styled, adapter="openai_responses", model_calls=1)


class SafeRenderer:
    """Uses Responses only when configured and always returns a template fallback."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> None:
        self.template = TemplateRenderer()
        self.live = (
            OpenAIResponsesRenderer(
                api_key=api_key,
                model=model,
                timeout_seconds=timeout_seconds,
                max_output_tokens=max_output_tokens,
            )
            if api_key
            else None
        )

    @property
    def configured_adapter(self) -> str:
        return "openai_responses" if self.live else "template"

    def render(self, plan: LessonPlan) -> RenderResult:
        if self.live is None:
            return RenderResult(
                lesson=self.template.render(plan), adapter="template", model_calls=0
            )
        try:
            return self.live.render(plan)
        except Exception as error:  # Provider, timeout, schema, and validation failures converge here.
            return RenderResult(
                lesson=self.template.render(plan),
                adapter="template",
                model_calls=1,
                fallback_reason=f"OPENAI_RENDER_FALLBACK:{type(error).__name__}",
            )

