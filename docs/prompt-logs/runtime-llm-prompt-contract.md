# Runtime LLM Prompt Contract

This file documents the only generative-model prompt used by the implemented tutor.

## Default behavior

The tutor does not require an LLM. If `OPENAI_API_KEY` is not configured, `SafeRenderer` uses `TemplateRenderer` and reports:

```json
{
  "adapter": "template",
  "model_calls": 0,
  "fallback_reason": null
}
```

The golden evaluation also disables the live renderer deliberately. Therefore, the submitted evaluation results contain **zero live LLM calls**.

## Exact runtime instruction

Source: `backend/app/adapters/openai_renderer.py`

```text
Select only a connective style for each approved lesson block. Do not add or rewrite academic content, equations, numbers, hints, or answers.
```

## Structured input

The model does not receive the raw learner event log, learner identity, canonical physics explanation, answer key, or free-form lesson content. It receives this shape:

```json
{
  "base_mode": "guided_solver",
  "modifiers": [
    "misconception_probe:balanced_forces_absent",
    "balanced"
  ],
  "blocks": [
    { "order": 1, "kind": "misconception_probe" },
    { "order": 2, "kind": "short_principle" },
    { "order": 3, "kind": "worked_example" }
  ]
}
```

The production call is created from the actual approved plan, so the number and order of blocks vary by policy and modifiers.

## Required structured output

The response must satisfy the `LiveRenderSelection` JSON schema:

```json
{
  "blocks": [
    { "order": 1, "connective_style": "encouraging" },
    { "order": 2, "connective_style": "concise" },
    { "order": 3, "connective_style": "reflective" }
  ]
}
```

Allowed values are limited to:

- `concise`
- `encouraging`
- `reflective`

Duplicate block orders are rejected. The returned order list must exactly equal the approved plan order.

## Deterministic application of the response

The selected value maps to one known lead-in:

| Style | Lead-in |
|---|---|
| `concise` | `Focus on this step.` |
| `encouraging` | `Take this one step at a time.` |
| `reflective` | `Pause and connect this step to what you already established.` |

`TemplateRenderer` then copies the approved prompt, explanation, and claim IDs. The LLM output never replaces those fields.

## Authority boundary

The runtime model may:

- Select one connective style for each already approved block.

The runtime model may not:

- Grade a learner response.
- Derive or write learner memory.
- Choose Foundation, Guided, or Challenge policy.
- Retrieve, author, or revise academic content.
- Change an equation, number, hint, answer, or explanation.
- Add, omit, duplicate, or reorder lesson blocks.
- Change the plan hash or allowed claim IDs.

## Provider settings and fallback

- API: OpenAI Responses API.
- Output: strict JSON schema.
- `store=False`.
- Maximum model calls per render: 1.
- Provider, timeout, schema, and validation errors converge to the deterministic template renderer.
- The fallback reason is recorded as `OPENAI_RENDER_FALLBACK:<ErrorType>`.

## Current logging behavior

The application trace records:

- `renderer_adapter`
- `renderer_version`
- `model_calls`
- `fallback_reason`
- `validation_result`
- `plan_hash`
- policy and catalog versions
- graph steps and total timing

The renderer also writes an append-only JSONL prompt record to `backend/data/runtime/prompt_logs/llm-calls.jsonl`. Because the renderer input contains only policy labels and block order/kind—not identity, learner history, academic content, answer keys, or credentials—the exact bounded request is retained for auditability.

For a provider call, the log shape is:

```json
{
  "schema_version": "1.0",
  "event_type": "llm_call",
  "prompt_log_id": "pl_...",
  "timestamp_utc": "...",
  "provider": "openai_responses",
  "provider_called": true,
  "outcome": "success",
  "input_hash": "sha256:...",
  "plan_hash": "sha256:...",
  "model": "configured-model-name",
  "request": {
    "instructions": "...",
    "input": "{...}",
    "text": {"format": {"type": "json_schema"}},
    "max_output_tokens": 500,
    "store": false
  },
  "response": {
    "response_id": "resp_...",
    "model": "configured-model-name",
    "output_text": "{...}",
    "usage": {}
  },
  "validation_result": "pass",
  "request_hash": "sha256:...",
  "response_hash": "sha256:...",
  "duration_ms": 420,
  "privacy": {
    "learner_identifier_logged": false,
    "credentials_logged": false,
    "raw_learner_history_logged": false
  }
}
```

When no key is configured, the same logger records `event_type=llm_call_skipped`, `provider_called=false`, `skip_reason=OPENAI_API_KEY_NOT_CONFIGURED`, and `response=null`. A provider, timeout, schema, or validation failure records `outcome=fallback` and the exception type without persisting the exception message.
