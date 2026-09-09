from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.api.schemas import DayNStartRequest  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.services.runtime import TutorRuntime  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for record in records
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run representative tutor flows and export their actual application logs."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "docs" / "prompt-logs",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Use the configured live renderer instead of forcing the deterministic "
            "template path. Produces real provider records; not byte-reproducible."
        ),
    )
    args = parser.parse_args()

    generated_at = datetime.now(UTC)
    run_id = f"app_log_{generated_at.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    runtime_root = BACKEND_ROOT / "data" / "runtime" / "log_exports" / run_id
    if args.live:
        config = Settings(runtime_dir=runtime_root)
    else:
        config = Settings(
            runtime_dir=runtime_root,
            OPENAI_API_KEY=None,
            LLM_BASE_URL=None,
            LLM_API_KEY=None,
        )
    runtime = TutorRuntime(config)
    if args.live and runtime.renderer.configured_adapter == "template":
        raise RuntimeError(
            "--live was requested but no live renderer is configured. Set LLM_BASE_URL "
            "and LLM_API_KEY (or OPENAI_API_KEY) in backend/.env."
        )

    scenarios = []
    trace_records = []
    for fixture_id in ("asha", "meera", "rohan", "isha"):
        result = runtime.start_dayn(
            DayNStartRequest(
                memory_fixture_id=fixture_id,
                session_goal="practice",
            )
        )
        trace = runtime.repository.load_trace(result.trace_id)
        session = runtime.repository.load_session(result.session_id)
        trace_records.append(trace.model_dump(mode="json", exclude_none=True))
        scenarios.append(
            {
                "fixture_id": fixture_id,
                "session_id": result.session_id,
                "trace_id": result.trace_id,
                "status": session.status,
                "plan_hash": trace.plan_hash,
                "renderer_adapter": trace.renderer_adapter,
                "model_calls": trace.model_calls,
            }
        )

    prompt_records = runtime.prompt_log.read_all()
    if not prompt_records:
        raise RuntimeError("The application run produced no renderer audit records.")
    if not args.live and any(record["provider_called"] for record in prompt_records):
        raise RuntimeError("This reproducible export must not make a live provider call.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = args.output_dir / "actual-application-prompt-logs.jsonl"
    trace_path = args.output_dir / "actual-application-agent-traces.jsonl"
    manifest_path = args.output_dir / "actual-application-log-manifest.json"
    readme_path = args.output_dir / "APPLICATION_LOG_EXPORT.md"
    checksum_path = args.output_dir / "SHA256SUMS.txt"

    # Copy the logger's bytes directly so the submitted prompt records are identical
    # to the application-generated runtime file.
    prompt_path.write_bytes(runtime.prompt_log.path.read_bytes())
    write_jsonl(trace_path, trace_records)

    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "generated_at_utc": generated_at.isoformat(),
        "source": "TutorRuntime.start_dayn using production application services",
        "runtime_root": str(runtime_root.relative_to(REPO_ROOT)),
        "execution_mode": {
            "renderer": runtime.renderer.configured_adapter,
            "model": runtime.renderer.model if args.live else None,
            "openai_api_key_configured": bool(args.live and config.openai_api_key),
            "live_provider_calls": sum(
                1 for record in prompt_records if record["provider_called"]
            ),
            "note": (
                (
                    "These are actual application records from live provider calls. "
                    "Each record carries the exact request, the provider response, "
                    "usage, validation outcome, and duration. Records with "
                    "outcome=fallback are genuine provider or validation failures that "
                    "were absorbed by the deterministic template renderer."
                )
                if args.live
                else (
                    "These are actual application records. The request payload is the exact "
                    "payload the bounded renderer would send, but provider_called=false and "
                    "response=null because no API key was configured. No response was fabricated."
                )
            ),
        },
        "scenarios": scenarios,
        "counts": {
            "scenarios": len(scenarios),
            "agent_traces": len(trace_records),
            "prompt_events": len(prompt_records),
            "provider_calls": sum(
                1 for record in prompt_records if record["provider_called"]
            ),
            "skipped_provider_calls": sum(
                1 for record in prompt_records if not record["provider_called"]
            ),
        },
        "privacy": {
            "credentials_in_logs": False,
            "raw_learner_identifiers_in_prompt_logs": False,
            "raw_learner_history_in_prompt_logs": False,
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    readme_path.write_text(
        """# Actual Application Log Export

This bundle was produced by executing four representative Day N scenarios through the real `TutorRuntime`, LangGraph workflow, policy engine, content retrieval, planner, validator, renderer, and trace repository.

## Delivered records

- `actual-application-prompt-logs.jsonl` contains the exact records written by the application renderer logger.
- `actual-application-agent-traces.jsonl` contains the four persisted agent execution traces.
- `actual-application-log-manifest.json` identifies the run, scenarios, execution mode, and counts.
- `SHA256SUMS.txt` provides integrity hashes for these files and this explanation.

## Important interpretation

This machine had no `OPENAI_API_KEY`, so the application correctly used its deterministic template renderer. Each prompt record therefore says `event_type=llm_call_skipped`, `provider_called=false`, `outcome=skipped`, `skip_reason=OPENAI_API_KEY_NOT_CONFIGURED`, and `response=null`.

The `request` object is still valuable: it is generated by the same `build_render_request` function used for a live Responses API call and shows the exact bounded instruction, structured input, JSON schema, model setting, token cap, and `store=false` setting for that plan. No provider response has been invented.

When a real API key is configured, the same logger writes `event_type=llm_call`, the exact request, provider response ID/model/output/usage, validation outcome, hashes, duration, and safe error type when fallback occurs. It never writes the API key, learner ID, or raw learner history.

## Correlation

Join a prompt event to an agent trace using `plan_hash`. The manifest maps each mock learner fixture to its session and trace IDs. The unsupported-content scenario produces an agent trace but no renderer prompt because the graph safely refuses before rendering.
""",
        encoding="utf-8",
        newline="\n",
    )

    delivered = [prompt_path, trace_path, manifest_path, readme_path]
    checksum_path.write_text(
        "\n".join(f"{sha256_file(path)}  {path.name}" for path in delivered) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(
        json.dumps(
            {
                "run_id": run_id,
                "mode": "live" if args.live else "reproducible",
                "renderer": runtime.renderer.configured_adapter,
                "prompt_events": len(prompt_records),
                "agent_traces": len(trace_records),
                "provider_calls": sum(
                    1 for record in prompt_records if record["provider_called"]
                ),
                "outcomes": {
                    outcome: sum(1 for r in prompt_records if r["outcome"] == outcome)
                    for outcome in sorted({r["outcome"] for r in prompt_records})
                },
                "output_dir": str(args.output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
