from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.models import ContentItem


def _normalise_unit(value: str) -> str:
    compact = re.sub(r"\s+", "", value.strip().casefold())
    compact = compact.replace("\u00b2", "^2")
    aliases = {
        "n": "n",
        "newton": "n",
        "newtons": "n",
        "m/s2": "m/s^2",
        "m/s^2": "m/s^2",
        "ms^-2": "m/s^2",
        "m/s/s": "m/s^2",
    }
    return aliases.get(compact, compact)


@dataclass(frozen=True)
class Grade:
    outcome: str
    score: float
    error_tags: tuple[str, ...]
    grader_confidence: float


def grade_response(item: ContentItem, value: str | float) -> Grade:
    key = item.answer_key
    if key is None:
        return Grade("ungradable", 0.0, (), 0.0)
    if key.kind == "numeric":
        match = re.fullmatch(
            r"\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*(.*?)\s*",
            str(value),
        )
        if not match:
            return Grade("ungradable", 0.0, (), 0.0)
        number = float(match.group(1))
        supplied_unit = match.group(2)
        if supplied_unit and key.unit and (
            _normalise_unit(supplied_unit) != _normalise_unit(key.unit)
        ):
            return Grade("incorrect", 0.0, ("unit_mismatch",), 1.0)
        correct = abs(number - float(key.value)) <= key.tolerance
        return Grade("correct" if correct else "incorrect", 1.0 if correct else 0.0, (), 1.0)
    normalised = str(value).strip().casefold()
    expected = str(key.value).strip().casefold()
    if key.kind == "choice":
        correct = normalised == expected
        return Grade("correct" if correct else "incorrect", 1.0 if correct else 0.0, (), 1.0)
    required = tuple(term.casefold() for term in key.required_terms)
    if normalised == expected or (required and all(term in normalised for term in required)):
        return Grade("correct", 1.0, (), 0.95)
    if len(normalised) < 2:
        return Grade("ungradable", 0.0, (), 0.0)
    return Grade("incorrect", 0.0, item.misconception_tags[:1], 0.9)
