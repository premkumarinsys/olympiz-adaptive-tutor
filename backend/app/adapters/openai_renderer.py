from __future__ import annotations

import json
from time import perf_counter
from typing import Any
from typing import Literal

from openai import OpenAI
from pydantic import Field, model_validator

from app.adapters.prompt_log import PromptLogStore
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
    adapter: Literal["template", "openai_responses", "chat_completions"]
    model_calls: int = Field(ge=0, le=1)
    fallback_reason: str | None = None


LEAD_INS = {
    "concise": "Focus on this step.",
    "encouraging": "Take this one step at a time.",
    "reflective": "Pause and connect this step to what you already established.",
}

RENDER_INSTRUCTIONS = (
    "Select only a connective style for each approved lesson block. "
    "Do not add or rewrite academic content, equations, numbers, hints, or answers."
)

# OpenAI strict mode enforces the schema server-side, so RENDER_INSTRUCTIONS can stay
# silent about shape. Compatible providers frequently treat response_format as a hint
# and invent their own keys, so state the contract explicitly for them. Enforcement
# still lives in LiveRenderSelection; this only raises the compliance rate.
CHAT_RENDER_INSTRUCTIONS = (
    RENDER_INSTRUCTIONS
    + ' Reply with JSON only, matching exactly:'
    + ' {"blocks":[{"order":<int>,"connective_style":<one of "concise","encouraging","reflective">}]}.'
    + " Include every order given, in the same sequence."
    + " Use no other keys and no other style values."
)


def render_input_json(plan: LessonPlan) -> str:
    """The only learner-derived payload any provider sees: mode, modifiers, block shape."""
    return json.dumps(
        {
            "base_mode": plan.decision.base_mode,
            "modifiers": plan.decision.modifiers,
            "blocks": [
                {"order": block.order, "kind": block.kind} for block in plan.blocks
            ],
        },
        separators=(",", ":"),
    )


def inline_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve $ref/$defs inline.

    Pydantic emits the nested block model as a $ref. OpenAI strict mode accepts
    that; several OpenAI-compatible providers do not, so flatten it for them.
    """
    defs = schema.get("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = defs.get(ref.rsplit("/", 1)[-1], {})
                overrides = {k: v for k, v in node.items() if k != "$ref"}
                return {**resolve(target), **overrides}
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)


def build_chat_render_request(
    plan: LessonPlan, *, model: str, max_output_tokens: int
) -> dict[str, Any]:
    """Chat Completions form of the same bounded request, for compatible providers."""
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": CHAT_RENDER_INSTRUCTIONS},
            {"role": "user", "content": render_input_json(plan)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "olympiz_render_selection",
                "strict": True,
                "schema": inline_schema(LiveRenderSelection.model_json_schema()),
            },
        },
        "max_tokens": max_output_tokens,
        "temperature": 0,
    }


def build_render_request(
    plan: LessonPlan, *, model: str, max_output_tokens: int
) -> dict[str, Any]:
    """Build the exact provider payload so execution and audit logs cannot drift."""
    return {
        "model": model,
        "instructions": RENDER_INSTRUCTIONS,
        "input": render_input_json(plan),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "olympiz_render_selection",
                "strict": True,
                "schema": LiveRenderSelection.model_json_schema(),
            },
            "verbosity": "low",
        },
        "max_output_tokens": max_output_tokens,
        "store": False,
    }


def _response_log_payload(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump(mode="json")
    elif usage is not None and not isinstance(usage, (dict, list, str, int, float, bool)):
        usage = None
    return {
        "response_id": getattr(response, "id", None),
        "model": getattr(response, "model", None),
        "output_text": getattr(response, "output_text", ""),
        "usage": usage,
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
        prompt_log: PromptLogStore | None = None,
        client: Any | None = None,
    ) -> None:
        self.client = client or OpenAI(api_key=api_key, timeout=timeout_seconds)
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.prompt_log = prompt_log
        self.template = TemplateRenderer()

    def render(self, plan: LessonPlan) -> RenderResult:
        request = build_render_request(
            plan, model=self.model, max_output_tokens=self.max_output_tokens
        )
        started = perf_counter()
        response = None
        try:
            response = self.client.responses.create(**request)
            selection = LiveRenderSelection.model_validate_json(response.output_text)
            expected_orders = [block.order for block in plan.blocks]
            actual_orders = [block.order for block in selection.blocks]
            if actual_orders != expected_orders:
                raise ValueError("renderer changed or omitted the approved block order")
        except Exception as error:
            if self.prompt_log is not None:
                self.prompt_log.append(
                    plan=plan,
                    model=self.model,
                    request=request,
                    provider="openai_responses",
                    provider_called=True,
                    outcome="fallback",
                    duration_ms=(perf_counter() - started) * 1000,
                    response=(
                        _response_log_payload(response) if response is not None else None
                    ),
                    error_type=type(error).__name__,
                )
            raise
        if self.prompt_log is not None:
            self.prompt_log.append(
                plan=plan,
                model=self.model,
                request=request,
                provider="openai_responses",
                provider_called=True,
                outcome="success",
                duration_ms=(perf_counter() - started) * 1000,
                response=_response_log_payload(response),
            )
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


def _chat_response_log_payload(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump(mode="json")
    elif usage is not None and not isinstance(usage, (dict, list, str, int, float, bool)):
        usage = None
    choices = getattr(response, "choices", None) or []
    content = ""
    if choices:
        content = getattr(getattr(choices[0], "message", None), "content", "") or ""
    return {
        "response_id": getattr(response, "id", None),
        "model": getattr(response, "model", None),
        "output_text": content,
        "usage": usage,
    }


class ChatCompletionsRenderer:
    """Same bounded style selection against any OpenAI-compatible Chat Completions API.

    Ollama Cloud, local Ollama, Gemini's compat layer and similar providers implement
    Chat Completions rather than Responses. The safety properties are unchanged: the
    model still only picks one enum per block and the approved order is re-validated.
    """

    version = "chat-completions-structured-1.0"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        prompt_log: PromptLogStore | None = None,
        client: Any | None = None,
    ) -> None:
        self.client = client or OpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout_seconds
        )
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.prompt_log = prompt_log
        self.template = TemplateRenderer()

    def render(self, plan: LessonPlan) -> RenderResult:
        request = build_chat_render_request(
            plan, model=self.model, max_output_tokens=self.max_output_tokens
        )
        started = perf_counter()
        response = None
        try:
            response = self.client.chat.completions.create(**request)
            payload = _chat_response_log_payload(response)
            selection = LiveRenderSelection.model_validate_json(payload["output_text"])
            expected_orders = [block.order for block in plan.blocks]
            actual_orders = [block.order for block in selection.blocks]
            if actual_orders != expected_orders:
                raise ValueError("renderer changed or omitted the approved block order")
        except Exception as error:
            if self.prompt_log is not None:
                self.prompt_log.append(
                    plan=plan,
                    model=self.model,
                    request=request,
                    provider="chat_completions",
                    provider_called=True,
                    outcome="fallback",
                    duration_ms=(perf_counter() - started) * 1000,
                    response=(
                        _chat_response_log_payload(response)
                        if response is not None
                        else None
                    ),
                    error_type=type(error).__name__,
                )
            raise
        if self.prompt_log is not None:
            self.prompt_log.append(
                plan=plan,
                model=self.model,
                request=request,
                provider="chat_completions",
                provider_called=True,
                outcome="success",
                duration_ms=(perf_counter() - started) * 1000,
                response=payload,
            )
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
        return RenderResult(lesson=styled, adapter="chat_completions", model_calls=1)


class SafeRenderer:
    """Uses a live renderer only when configured and always returns a template fallback."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        prompt_log: PromptLogStore | None = None,
        base_url: str | None = None,
        live_api_key: str | None = None,
        live_model: str | None = None,
    ) -> None:
        self.template = TemplateRenderer()
        self.max_output_tokens = max_output_tokens
        self.prompt_log = prompt_log
        self.live: Any | None = None
        self.provider = "none"
        # An explicitly configured compatible endpoint wins over a bare OPENAI_API_KEY.
        if base_url and live_api_key:
            self.model = live_model or model
            self.provider = "chat_completions"
            self.live = ChatCompletionsRenderer(
                api_key=live_api_key,
                base_url=base_url,
                model=self.model,
                timeout_seconds=timeout_seconds,
                max_output_tokens=max_output_tokens,
                prompt_log=prompt_log,
            )
        elif api_key:
            self.model = model
            self.provider = "openai_responses"
            self.live = OpenAIResponsesRenderer(
                api_key=api_key,
                model=model,
                timeout_seconds=timeout_seconds,
                max_output_tokens=max_output_tokens,
                prompt_log=prompt_log,
            )
        else:
            self.model = model

    @property
    def configured_adapter(self) -> str:
        return self.provider if self.live else "template"

    def _skipped_request(self, plan: LessonPlan) -> dict[str, Any]:
        return build_render_request(
            plan, model=self.model, max_output_tokens=self.max_output_tokens
        )

    def render(self, plan: LessonPlan) -> RenderResult:
        if self.live is None:
            if self.prompt_log is not None:
                self.prompt_log.append(
                    plan=plan,
                    model=self.model,
                    request=self._skipped_request(plan),
                    provider="none",
                    provider_called=False,
                    outcome="skipped",
                    duration_ms=0,
                    skip_reason="OPENAI_API_KEY_NOT_CONFIGURED",
                )
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
