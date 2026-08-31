# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## Selected Product Direction

- Recreate references/selected-design.png as the visual source of truth.
- Use the guided learning journey: pale sand surfaces, forest-green primary actions, cobalt links, coral only for misconception attention, restrained borders, and minimal elevation.
- Preserve the visible hierarchy: compact header, left goal/memory rail, four-stage progress path, one active lesson task, and bottom session-summary band.
- Student interaction remains primary; reviewer evidence opens through a compact decision-trace control.
- The project includes a deterministic FastAPI backend in backend/; frontend source stays in src/.
