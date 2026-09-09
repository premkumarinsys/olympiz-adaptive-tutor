# Olympiz deterministic backend

FastAPI modular monolith for the Day 0, Day N, and Open Chat adaptive-tutor work
trial. Bounded LangGraph workflows make the core lesson, open conversation,
exercise generation, and revision flows explicit and inspectable. Verified
content, learner-state reduction, policy, trusted exercise solving, grading,
safety, and memory writes remain deterministic.

## Run

From `backend/`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Use `py -3.12` and the explicit `.\.venv\Scripts\python.exe` path rather than a
bare `python` or shell activation. Bare `python` can resolve to a different
interpreter than the venv was built against, and re-running `python -m venv .venv`
over an existing environment replaces the interpreter but keeps the old
`site-packages`, leaving compiled wheels that no longer match. That surfaces as
`ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'`; the fix is
to delete `.venv` and recreate it.

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## Verify

```powershell
.\.venv\Scripts\python.exe scripts\run_evaluation.py
```

The reviewer gate intentionally uses this one golden evaluation rather than a
generic API integration suite or linting stack. Focused reducer and policy unit
tests remain under `tests/unit/` and can be run with `pytest` if installed.

The evaluation endpoint is `POST /api/v1/evaluations`. Its results measure
deterministic behavior on synthetic fixtures, not real learning gains.

## Agent graph

The typed graph in `app/services/agent_graph.py` has explicit nodes for input
validation, memory reduction, policy selection, verified retrieval and planning,
rendering, output validation, one template fallback, safe refusal, and finalization.
It cannot recurse: a render validation failure receives at most one deterministic
fallback before refusal.

Day 0 setup and intermediate diagnostic turns take the bounded state-only route.
Placement and Day N lesson creation take the full policy/plan/render route. The
trace records every graph node, renderer adapter, fallback reason, and model-call
count.

## Open Chat and revision

The Open Chat API keeps the teacher-authored lesson fixed while adapting
explanations, scaffolding, practice, and revision from the learner's reduced
memory. It supports `ask`, `prepare`, `practice`, `revise`, and `answer`
actions under `/api/v1/chat/sessions`.

Dynamic exercises use a separate three-node graph. The configured model can
propose only an approved scenario and bounded numeric parameters. Backend code
selects the target concept and difficulty, validates the response, writes the
question, computes the answer, checks units, and keeps the answer key out of the
public payload. Invalid, duplicate, unavailable, or mistargeted generation falls
back to the verified catalog.

The revision planner combines mastery, uncertainty, staleness, misconceptions,
and retention estimates to build a targeted exercise set and ordered schedule.
The operation is integrated into the agent graph and validated in the unit
suite. Open Chat currently exposes targeted revision practice; the full schedule
does not yet have a separate endpoint or UI.

## Optional model providers

Deterministic template rendering is the default and requires no secret. Set
`OPENAI_API_KEY` to enable the optional OpenAI Responses adapter. The model is
configurable with `OPENAI_MODEL`; the default is `gpt-5-mini`.

```powershell
$env:OPENAI_API_KEY = "..."
$env:OPENAI_MODEL = "gpt-5-mini"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

An OpenAI-compatible Chat Completions provider can instead use `LLM_BASE_URL`,
`LLM_API_KEY`, and `LLM_MODEL`.

For a Day 0 or Day N rendered plan, the Responses adapter makes at most one
strict-schema call with a six-second default timeout, a 500-token output cap,
and `store=False`. That call selects connective style only and cannot change
content, claims, answers, block order, policy, or memory. Open Chat uses the
same configured client through separate prompts for lesson-grounded conversation
and bounded exercise parameters. Provider, timeout, schema, or validation
failures use deterministic fallbacks. The golden evaluation always disables the
live provider even when the environment contains a key.

Each renderer decision is appended to `data/runtime/prompt_logs/llm-calls.jsonl`.
Live calls record the exact bounded request, provider response, validation result,
duration, and hashes. With no key, the record explicitly says the call was
skipped and keeps `response` as `null`; no response is fabricated. The logger
does not write credentials, learner identifiers, or raw learner history.

Generate the checked-in, reproducible application-log bundle with:

```powershell
.\.venv\Scripts\python.exe scripts\generate_application_logs.py
```

## Safety boundary

- The browser never supplies answer keys or rubrics.
- Every physics-bearing block references the pinned verified catalog.
- Unsupported topics return a successful `safe_refusal` outcome.
- The core lesson renderer places the optional model downstream of the approved
  plan. Open Chat gives the model no memory-write or grading capability, and its
  generated exercise parameters are solved and checked by trusted code.
- Events are append-only; snapshots are derived and expendable.
- The trial JSONL adapter is designed for a single local worker. Production
  should use transactional storage with a learner/idempotency unique constraint.
