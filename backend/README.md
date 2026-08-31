# Olympiz deterministic backend

FastAPI modular monolith for the Day 0 and Day N adaptive-tutor work trial. A
bounded LangGraph state machine makes the agent loop explicit and inspectable.
Verified content, learner-state reduction, policy, retrieval, lesson structure,
grading, safety, and memory remain deterministic.

## Run

From `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## Verify

```powershell
python scripts\run_evaluation.py
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

## Optional OpenAI renderer

Deterministic template rendering is the default and requires no secret. Set
`OPENAI_API_KEY` to enable the optional OpenAI Responses adapter. The model is
configurable with `OPENAI_MODEL`; the default is `gpt-5-mini`.

```powershell
$env:OPENAI_API_KEY = "..."
$env:OPENAI_MODEL = "gpt-5-mini"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The adapter makes at most one Responses API call for a rendered plan, uses a
strict JSON schema, has a six-second default timeout and 500-token output cap,
and sets `store=False`. The model selects only connective style. It cannot
change content, claims, answers, block order, policy, or memory. Provider,
timeout, schema, or validation failures use `TemplateRenderer` automatically.
The deterministic evaluation always disables the live renderer even when the
environment contains an API key.

## Safety boundary

- The browser never supplies answer keys or rubrics.
- Every physics-bearing block references the pinned verified catalog.
- Unsupported topics return a successful `safe_refusal` outcome.
- The optional model is downstream of the approved plan and never receives a
  memory-write or grading capability.
- Events are append-only; snapshots are derived and expendable.
- The trial JSONL adapter is designed for a single local worker. Production
  should use transactional storage with a learner/idempotency unique constraint.
