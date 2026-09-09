"""Map a learner's free-text explanation onto an item's own authored tags.

The model proposes; a validator disposes. It never sees the answer key, never grades,
and never writes memory. Any tag outside the item's authored vocabulary invalidates the
whole result, which degrades to `unclassified`.
"""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Literal

from openai import OpenAI
from pydantic import Field

from app.adapters.openai_renderer import inline_schema

from app.domain.models import StrictModel

CLASSIFIER_VERSION = "reasoning-clf-1.0"

CLASSIFY_INSTRUCTIONS = (
    "A student explained how they solved a physics problem. Decide which of the listed "
    "verified claims their explanation correctly invokes, and which of the listed "
    "misconceptions it exhibits. Judge only what the student actually wrote. Do not "
    "grade the answer, infer ability, or use any tag that is not listed. "
    'Reply with JSON only, matching exactly: '
    '{"claims_invoked":[<ids>],"misconceptions_exhibited":[<tags>]}. '
    "Use only ids and tags from the lists given. Return empty lists if nothing matches."
)


class ClassificationSelection(StrictModel):
    claims_invoked: tuple[str, ...] = ()
    misconceptions_exhibited: tuple[str, ...] = ()


class ClassificationResult(StrictModel):
    claims_invoked: tuple[str, ...] = ()
    misconceptions_exhibited: tuple[str, ...] = ()
    outcome: Literal["classified", "unclassified", "classifier_error"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    classifier_version: str | None = None
    classifier_model: str | None = None
    error_type: str | None = None


def build_classify_request(
    *,
    reasoning_text: str,
    claim_ids: tuple[str, ...],
    misconception_tags: tuple[str, ...],
    model: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    """The exact provider payload, so execution and audit logs cannot drift."""
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": CLASSIFY_INSTRUCTIONS},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "available_claims": list(claim_ids),
                        "available_misconceptions": list(misconception_tags),
                        "student_explanation": reasoning_text,
                    },
                    separators=(",", ":"),
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "olympiz_reasoning_classification",
                "strict": True,
                "schema": inline_schema(ClassificationSelection.model_json_schema()),
            },
        },
        "max_tokens": max_output_tokens,
        "temperature": 0,
    }


class ReasoningClassifier:
    """Bounded classifier over an OpenAI-compatible Chat Completions endpoint."""

    version = CLASSIFIER_VERSION

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str | None,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int = 600,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.client = client
        if self.client is None and api_key:
            self.client = OpenAI(
                api_key=api_key, base_url=base_url or None, timeout=timeout_seconds
            )

    @property
    def configured(self) -> bool:
        return self.client is not None

    def classify(
        self,
        *,
        reasoning_text: str,
        claim_ids: tuple[str, ...],
        misconception_tags: tuple[str, ...],
    ) -> ClassificationResult:
        if not reasoning_text.strip():
            return ClassificationResult(outcome="unclassified")
        if self.client is None:
            return ClassificationResult(
                outcome="classifier_error", error_type="CLASSIFIER_NOT_CONFIGURED"
            )
        request = build_classify_request(
            reasoning_text=reasoning_text,
            claim_ids=claim_ids,
            misconception_tags=misconception_tags,
            model=self.model,
            max_output_tokens=self.max_output_tokens,
        )
        try:
            response = self.client.chat.completions.create(**request)
            content = response.choices[0].message.content or ""
            selection = ClassificationSelection.model_validate_json(content)
        except Exception as error:
            return ClassificationResult(
                outcome="classifier_error", error_type=type(error).__name__
            )

        # Closed vocabulary: one tag outside the item's own lists invalidates everything.
        allowed_claims = set(claim_ids)
        allowed_misconceptions = set(misconception_tags)
        if not set(selection.claims_invoked) <= allowed_claims or not set(
            selection.misconceptions_exhibited
        ) <= allowed_misconceptions:
            return ClassificationResult(
                outcome="unclassified", error_type="OUT_OF_VOCABULARY"
            )

        if not selection.claims_invoked and not selection.misconceptions_exhibited:
            return ClassificationResult(
                outcome="unclassified",
                classifier_version=self.version,
                classifier_model=self.model,
            )

        return ClassificationResult(
            claims_invoked=tuple(dict.fromkeys(selection.claims_invoked)),
            misconceptions_exhibited=tuple(
                dict.fromkeys(selection.misconceptions_exhibited)
            ),
            outcome="classified",
            classifier_version=self.version,
            classifier_model=self.model,
        )
