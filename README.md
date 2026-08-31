# Olympiz adaptive tutor work trial

An end-to-end local prototype for the Meraki Labs / Olympiz AI Engineer work trial. It demonstrates Day 0 cold-start diagnosis, Day N personalization from event-sourced memory, deterministic policy and lesson planning, verified-content retrieval, a bounded LangGraph agent loop, optional LLM-assisted rendering, safe refusal/slowdown, reviewer traces, side-by-side comparison, and a fixed evaluation suite.

The implementation is deliberately local and reproducible. It works without an LLM key by using the verified template renderer. When `OPENAI_API_KEY` is present, one constrained OpenAI Responses call may select connective style for an approved lesson; it cannot grade, choose policy, alter physics content, or write learner memory.

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

Open `http://127.0.0.1:5173`. Vite proxies `/api` to the local FastAPI service. The student experience remains runnable with deterministic mock fallback data if the API is unavailable.

To enable the optional live renderer before starting the backend:

```powershell
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "gpt-5-mini"
```

Without those variables, the same graph runs with zero model calls and the deterministic renderer.

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
.\.venv\Scripts\python.exe scripts\run_evaluation.py

cd D:\olympiz-adaptive-tutor
npm run build
```

The work-trial gate is intentionally small: one golden evaluation command and one frontend production build. Generic API integration testing and lint tooling were removed from the trial scope. Focused reducer and policy unit tests remain available through the optional `dev` dependency.

## Reviewer path

1. Start a Day 0 diagnostic and complete the cold-start placement flow.
2. Open Day N and compare Kabir, Dev, and Isha to see misconception handling, safe slowdown, and safe refusal.
3. Use **Compare learners** to inspect deterministic plan differences.
4. Run **Evaluation** to verify the eight golden fixture policies.
5. Open the reviewer trace drawer during a lesson to inspect evidence, rule, policy, content, latency, and hash provenance.

## Project map

- `src/` — React student and reviewer experience.
- `backend/app/services/agent_graph.py` — bounded LangGraph state, nodes, and routing.
- `backend/app/adapters/openai_renderer.py` — optional structured OpenAI Responses adapter and verified fallback.
- `backend/app/` — FastAPI modular monolith, learner reducer, policy, planner, catalog, grader, safety, and persistence.
- `backend/data/` — 18 verified mechanics items, eight learner fixtures, and local runtime JSONL.
- `backend/scripts/run_evaluation.py` — the single reviewer-facing golden evaluation.
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
