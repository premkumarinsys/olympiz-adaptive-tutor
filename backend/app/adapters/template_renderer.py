from __future__ import annotations

from app.domain.models import LessonPlan, StrictModel


class RenderedBlock(StrictModel):
    order: int
    kind: str
    prompt: str
    explanation: str
    claim_ids: tuple[str, ...]


class RenderedLesson(StrictModel):
    plan_hash: str
    renderer_version: str = "template-1.0"
    blocks: tuple[RenderedBlock, ...]


class TemplateRenderer:
    """Reference renderer: copies only already-approved plan material."""

    version = "template-1.0"

    def render(self, plan: LessonPlan) -> RenderedLesson:
        return RenderedLesson(
            plan_hash=plan.plan_hash,
            renderer_version=self.version,
            blocks=tuple(
                RenderedBlock(
                    order=block.order,
                    kind=block.kind,
                    prompt=block.prompt,
                    explanation=block.explanation,
                    claim_ids=block.claim_ids,
                )
                for block in plan.blocks
            ),
        )

