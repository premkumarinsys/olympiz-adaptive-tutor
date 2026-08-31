from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from app.core.canonical import content_hash
from app.domain.models import (
    CandidateExclusion,
    Catalog,
    ContentItem,
    ContentQuery,
    ContentSelection,
)


class ContentCatalog:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self._by_id = {item.content_id: item for item in catalog.items}

    @classmethod
    def load(cls, path: Path) -> ContentCatalog:
        data = json.loads(path.read_text(encoding="utf-8"))
        catalog = TypeAdapter(Catalog).validate_python(data)
        if len(catalog.items) != len({item.content_id for item in catalog.items}):
            raise ValueError("content IDs must be unique")
        for item in catalog.items:
            missing = set(item.claim_ids) - set(catalog.claims)
            if missing:
                raise ValueError(f"{item.content_id} references unknown claims: {sorted(missing)}")
        return cls(catalog)

    def get(self, content_id: str) -> ContentItem:
        return self._by_id[content_id]

    def supports(self, concept_id: str) -> bool:
        return concept_id in self.catalog.supported_concepts

    def retrieve(self, query: ContentQuery) -> ContentSelection:
        exclusions: list[CandidateExclusion] = []
        candidates: list[tuple[float, ContentItem]] = []
        for item in self.catalog.items:
            reason = None
            if item.status != "verified":
                reason = "NOT_VERIFIED"
            elif item.content_id in query.excluded_content_ids:
                reason = "RECENTLY_USED"
            elif item.pedagogy != query.pedagogy:
                reason = "PEDAGOGY_MISMATCH"
            elif item.locale != query.locale:
                reason = "LOCALE_MISMATCH"
            elif item.concept_id not in {query.concept_id, "net_force", "vectors"}:
                reason = "CONCEPT_MISMATCH"
            elif item.exam_targets and query.exam_goal not in item.exam_targets:
                reason = "EXAM_MISMATCH"
            elif query.misconception_tags and not (
                set(query.misconception_tags) & set(item.misconception_tags)
            ):
                reason = "MISCONCEPTION_MISMATCH"
            if reason:
                exclusions.append(CandidateExclusion(content_id=item.content_id, reason_code=reason))
                continue
            difficulty_fit = max(0.0, 1.0 - abs(item.difficulty - query.difficulty) / 4)
            misconception = float(
                bool(set(query.misconception_tags) & set(item.misconception_tags))
            )
            representation = 1.0 if item.representation == query.representation else 0.0
            score = 4 * difficulty_fit + 3 * misconception + representation
            candidates.append((score, item))
        candidates.sort(key=lambda candidate: (-candidate[0], candidate[1].content_id))
        selected = candidates[0][1] if candidates else None
        return ContentSelection(
            selected=selected,
            selection_reasons=("VERIFIED", "STABLE_CONTENT_ID_TIEBREAK") if selected else (),
            exclusions=tuple(exclusions),
            query_hash=content_hash(query),
        )

