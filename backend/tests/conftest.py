import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from app.domain.models import LearnerFixture

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def fixtures() -> dict[str, LearnerFixture]:
    data = json.loads((ROOT / "data" / "fixtures" / "learners.json").read_text(encoding="utf-8"))
    values = TypeAdapter(list[LearnerFixture]).validate_python(data)
    return {value.fixture_id: value for value in values}

