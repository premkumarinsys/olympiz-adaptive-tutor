from __future__ import annotations

from typing import Protocol

from app.domain.models import ContentItem, ContentQuery, ContentSelection, LessonPlan
from app.services.grader import Grade


class GraderTool(Protocol):
    version: str

    def grade(self, request_id: str, item: ContentItem, response: str | float) -> Grade: ...


class ContentTool(Protocol):
    def get_next_content(self, request_id: str, query: ContentQuery) -> ContentSelection: ...


class RendererTool(Protocol):
    version: str

    def render(self, plan: LessonPlan): ...

