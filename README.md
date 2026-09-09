# Olympiz adaptive tutor work trial

An end-to-end local prototype for the Meraki Labs / Olympiz AI Engineer work trial. It demonstrates Day 0 cold-start diagnosis, Day N personalization from event-sourced memory, a fixed teacher-authored class lesson, an open chat tutor, memory-targeted practice and revision, constrained LLM-generated exercises, deterministic policy and lesson planning, verified-content retrieval, bounded LangGraph workflows, safe refusal/slowdown, reviewer traces, side-by-side comparison, and a fixed evaluation suite.

The implementation is deliberately local and reproducible. It works without an LLM key by using verified lesson and exercise fallbacks. When a provider is configured, the model can answer lesson-grounded questions, select connective style, and propose bounded exercise parameters. Trusted backend code still chooses the learning policy, authors and solves exercises, validates units, grades responses, and writes learner memory.

For a shareable overview of the latest experience, architecture, demo path, validation, and prototype boundaries, see [Latest work-trial features](docs/work-trial-latest-features.md).

## Run locally

Use two PowerShell terminals.

Backend:

```powershell
cd D:\olympiz-adaptive-tutor\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Create the environment with `py -3.12`, not bare `python`. A bare `python` may
resolve to a different interpreter than the one already on the machine, and
re-running `python -m venv .venv` over an existing `.venv` swaps the interpreter
while leaving the previously installed packages in place. The result is a venv
whose compiled wheels no longer match its Python, which fails at import with
`ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'`. If that
happens, delete `.venv` and recreate it with the command above.

Frontend:

```powershell
cd D:\olympiz-adaptive-tutor
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The Open Chat Tutor is at `http://127.0.0.1:5173/chat`. Vite proxies `/api` to the local FastAPI service. The student experience remains runnable with deterministic mock fallback data if the API is unavailable.

To enable the live OpenAI features before starting the backend:

```powershell
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "gpt-5-mini"
```

An OpenAI-compatible Chat Completions provider can also be configured with `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`. Without a configured provider, the same workflows use the deterministic renderer, a limited lesson guide, and verified practice-bank exercises.

Renderer decisions are written to `backend/data/runtime/prompt_logs/llm-calls.jsonl`. Live mode records the exact bounded request and validated response; template mode records that the provider call was skipped and why. The logger never stores the API key, learner identity, or raw learner history. A checked-in application-run bundle and integrity hashes are indexed in [`PROMPT_LOGS.md`](PROMPT_LOGS.md).

## Agent loop

Each session action invokes one typed, non-recursive LangGraph workflow:

```text
validate input
  -> reduce immutable learner events
  -> choose deterministic policy
  -> retrieve verified content and build a fixed lesson plan
  -> optional one-call LLM style selection
  -> validate plan, claims, block order, and canonical content
  -> return lesson
```

If content is unsupported, the graph routes to `safe_refusal`. If the live renderer times out, returns invalid JSON, or changes the approved structure, it routes once through `TemplateRenderer`; a second failure refuses safely. The JSONL event store is the authoritative long-term memory. LangGraph coordinates execution but is not allowed to mutate memory directly.

## Verify

```powershell
cd D:\olympiz-adaptive-tutor\backend
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe scripts\run_evaluation.py

cd D:\olympiz-adaptive-tutor
npm run build
npm run test:sites
```

The work-trial gate is intentionally small: one golden evaluation command and one frontend production build. Generic API integration testing and lint tooling were removed from the trial scope. Focused reducer and policy unit tests remain available through the optional `dev` dependency.

## Reviewer path

1. Open **Your open chat tutor**, select Asha, Kabir, or Meera, and compare how the same class lesson receives different support.
2. Use **Explore**, **Prepare**, **Practice**, and **Revise**; submit an answer and confirm that checked work updates learner memory.
3. Start a Day 0 diagnostic and complete the cold-start placement flow.
4. Open Day N and compare Kabir, Dev, and Isha to see misconception handling, safe slowdown, and safe refusal.
5. Use **Compare learners** to inspect deterministic plan differences.
6. Run **Evaluation** to verify the eight golden fixture policies.
7. Open a decision trace to inspect evidence, rules, provider source, content provenance, and validation.

## Project map

- `src/` — React student and reviewer experience.
- `backend/app/services/agent_graph.py` — bounded LangGraph state, nodes, and routing.
- `backend/app/services/chat_tutor.py` — fixed-lesson open conversation, exercise delivery, grading, and session isolation.
- `backend/app/services/exercise_generator.py` — constrained parameter generation with backend-authored and backend-solved exercises.
- `backend/app/services/revision_planner.py` — retention-aware concept ranking, exercise-set creation, and spaced revision scheduling.
- `backend/app/adapters/openai_renderer.py` — optional structured OpenAI Responses adapter and verified fallback.
- `backend/app/` — FastAPI modular monolith, learner reducer, policy, planner, catalog, grader, safety, and persistence.
- `backend/data/` — 18 verified mechanics items, eight learner fixtures, and local runtime JSONL.
- `backend/scripts/run_evaluation.py` — the single reviewer-facing golden evaluation.
- `backend/scripts/generate_application_logs.py` — runs four representative scenarios and exports actual application prompt/trace logs.
- `PROMPT_LOGS.md` — index and interpretation guide for the checked-in application log bundle.
- `docs/work-trial-latest-features.md` — shareable latest-feature brief, architecture, demo path, evidence, and limitations.
- `docs/open-chat-tutor.md` — detailed Open Chat design and implementation contract.
- `backend/tests/unit/` — focused reducer, policy, plan, determinism, and safety unit tests.
- `docs/01-product-idea-and-solution-architecture.md` — detailed problem framing, product idea, requirements, solution architecture, agent flow, safety, evaluation, roadmap, and presentation narrative.
- `docs/02-code-files-methods-architecture.md` — engineer onboarding guide covering files, domain models, classes, methods, endpoints, call paths, extension points, debugging, and verification.
- `output/pdf/Olympiz_Product_Idea_and_Solution_Architecture.pdf` — presentation-ready PDF edition with contents, rendered architecture figures, and page navigation.
- `output/pdf/Olympiz_Code_Files_and_Methods_Architecture.pdf` — engineer-facing PDF edition with file maps, method tables, execution diagrams, and extension guidance.
- `docs/solution-design.md` — detailed product, architecture, data, evaluation, failure, and scale design.
- `docs/architecture-and-presentation-guide.md` — implementation-aligned architecture guide, slide storyboard, demo script, and reviewer Q&A.
- `references/selected-design.png` — selected Option 3 visual target.

## Scope and safety

The trial supports a curated mechanics slice only. Unsupported concepts return `safe_refusal`; contradictory or insufficient evidence returns a provisional guided policy. Memory is append-only and derived state is recomputed from validated events. Production evolution would replace local JSONL with transactional storage and add authentication, consent/retention controls, quotas, and observability.
