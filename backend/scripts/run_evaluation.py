"""Run the deterministic golden evaluation without starting the API server."""

from __future__ import annotations

import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.api.schemas import EvaluationRequest  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.services.runtime import TutorRuntime  # noqa: E402


def main() -> int:
    settings = Settings(
        data_dir=BACKEND_ROOT / "data",
        runtime_dir=BACKEND_ROOT / "data" / "runtime",
        openai_api_key=None,
    )
    report = TutorRuntime(settings).evaluate(EvaluationRequest(repeat_runs=20))
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

