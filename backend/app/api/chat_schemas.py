from __future__ import annotations

from typing import Literal
from pydantic import Field, model_validator
from app.domain.models import StrictModel


class ChatStartRequest(StrictModel):
    memory_fixture_id: str | None = None
    learner_id: str | None = None

    @model_validator(mode="after")
    def one_source(self):
        if (self.memory_fixture_id is None) == (self.learner_id is None):
            raise ValueError("Provide exactly one learner memory source")
        return self


class ChatMessageRequest(StrictModel):
    client_turn_id: str = Field(min_length=1, max_length=120)
    message: str = Field(default="", max_length=4000)
    action: Literal["ask", "prepare", "practice", "revise", "answer"] = "ask"
    exercise_id: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    hints_used: bool = False

    @model_validator(mode="after")
    def needs_text(self):
        if self.action in {"ask", "answer"} and not self.message.strip():
            raise ValueError("A message is required")
        if self.action == "answer" and not self.exercise_id:
            raise ValueError("An exercise ID is required")
        return self
