import { demoActivities as defaultDemoActivities, demoCompare, demoEvaluation, demoTrace, guidedActivity, mockLearners } from "./demoData";
import type {
  Activity,
  CompareResponse,
  EvaluationResponse,
  MockLearner,
  ReviewerTrace,
  StartSessionResponse,
  TurnResponse,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

type BackendActivity = Omit<Activity, "kind"> & { kind: string };

type BackendFixture = {
  fixture_id: string;
  display_name: string;
  scenario: string;
  default_topic_id: string;
  expected_base_mode: string;
  expected_modifiers: string[];
};

const readable = (value: unknown) =>
  String(value ?? "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

function normalizeActivity(activity: BackendActivity | null | undefined): Activity | null {
  if (!activity) return null;
  const kind = activity.kind === "choice" ? "multiple_choice" : activity.kind === "text" ? "short_text" : activity.kind;
  return { ...activity, kind: kind as Activity["kind"] };
}

function fixtureToLearner(fixture: BackendFixture): MockLearner {
  const local = mockLearners.find((learner) => learner.learner_id === fixture.fixture_id);
  const modifiers = [...fixture.expected_modifiers];
  return {
    ...(local ?? mockLearners[3]),
    learner_id: fixture.fixture_id,
    name: fixture.display_name,
    scenario: fixture.scenario,
    base_mode: readable(fixture.expected_base_mode),
    modifiers,
    memory_preview: {
      ...(local?.memory_preview ?? mockLearners[3].memory_preview),
      summary: fixture.scenario,
      active_strategy: readable(fixture.expected_base_mode),
      modifiers,
    },
  };
}

function normalizeStartSession(raw: any, fixtureId?: string): StartSessionResponse {
  const local = mockLearners.find((learner) => learner.learner_id === fixtureId) ?? mockLearners[3];
  const decision = raw.decision ?? {};
  const learner = fixtureId
    ? {
        ...local,
        name: raw.learner_summary?.display_name ?? local.name,
        scenario: raw.learner_summary?.scenario ?? local.scenario,
        base_mode: readable(decision.base_mode || local.base_mode),
        modifiers: decision.modifiers ?? local.modifiers,
        memory_preview: {
          ...local.memory_preview,
          summary: raw.learner_summary?.scenario ?? local.memory_preview.summary,
          active_strategy: readable(decision.base_mode || local.memory_preview.active_strategy),
          modifiers: decision.modifiers ?? local.memory_preview.modifiers,
          warning: decision.provisional
            ? "The current strategy is provisional while the tutor collects cleaner evidence."
            : local.memory_preview.warning,
        },
      }
    : undefined;
  return {
    session_id: raw.session_id,
    mode: raw.mode,
    diagnostic_stage: raw.diagnostic_stage ?? undefined,
    next_activity: normalizeActivity(raw.next_activity),
    trace_id: raw.trace_id,
    learner,
    memory_preview: learner?.memory_preview,
  };
}

function normalizeTrace(raw: any): ReviewerTrace {
  const timings = raw.timings_ms ?? {};
  return {
    trace_id: raw.trace_id,
    status: raw.validation_result ?? "validated",
    plan_hash: raw.plan_hash ?? "no-plan-hash",
    versions: {
      policy: raw.policy_version ?? "unknown",
      catalog: raw.catalog_version ?? "unknown",
      renderer: raw.renderer_version ?? "unknown",
      grader: raw.grader_version ?? "unknown",
    },
    pipeline: (raw.pipeline ?? []).map((name: string) => ({ name, status: "complete" as const })),
    evidence: (raw.evidence_used ?? []).map((eventId: string) => ({
      observation: eventId,
      weight: "Recorded event",
      use: "Included in the deterministic learner-state reduction.",
    })),
    rules: (raw.rules ?? []).map((rule: any) => ({
      id: rule.rule_id ?? "policy-rule",
      detail: `${rule.metric ?? "evidence"} ${rule.operator ?? ""} ${JSON.stringify(rule.threshold ?? "")}`,
      result: readable(rule.selected_action ?? "applied"),
    })),
    state_diff: [],
    timings: Object.entries(timings).map(([phase, ms]) => ({ phase, ms: Number(ms) })),
  };
}

export class ApiError extends Error {
  code: string;
  retryable: boolean;
  traceId?: string;
  status: number;

  constructor(message: string, options: { code?: string; retryable?: boolean; traceId?: string; status?: number } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = options.code ?? "REQUEST_FAILED";
    this.retryable = options.retryable ?? false;
    this.traceId = options.traceId;
    this.status = options.status ?? 0;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 8_000);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      signal: controller.signal,
    });
    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) {
      throw new ApiError("The API returned an unexpected response.", { status: response.status, retryable: response.status >= 500 });
    }
    const payload = await response.json();
    if (!response.ok) {
      const error = payload?.error ?? {};
      throw new ApiError(error.message ?? "Request failed.", {
        code: error.code,
        retryable: error.retryable,
        traceId: error.trace_id,
        status: response.status,
      });
    }
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("The tutor took too long to respond.", { code: "TIMEOUT", retryable: true });
    }
    throw new ApiError("The local API is unavailable.", { code: "API_UNAVAILABLE", retryable: true });
  } finally {
    window.clearTimeout(timeout);
  }
}

function withDemoFallback<T>(remote: () => Promise<T>, fallback: () => T | Promise<T>): Promise<T> {
  return remote().catch((error) => {
    if (error instanceof ApiError && (error.code === "API_UNAVAILABLE" || error.status === 404)) {
      return fallback();
    }
    throw error;
  });
}

let demoDay0Index = 0;

export const api = {
  getMockLearners(): Promise<MockLearner[]> {
    return withDemoFallback(
      () => request<{ learners: BackendFixture[] }>("/api/v1/mock-learners").then((payload) => payload.learners.map(fixtureToLearner)),
      () => mockLearners,
    );
  },

  startDay0(input: Record<string, unknown>): Promise<StartSessionResponse> {
    return withDemoFallback(
      () => request<any>("/api/v1/day0/sessions", { method: "POST", body: JSON.stringify(input) }).then((raw) => normalizeStartSession(raw)),
      () => {
        demoDay0Index = 0;
        return {
          session_id: `demo-day0-${Date.now()}`,
          mode: "day0",
          diagnostic_stage: "prerequisite_probe",
          next_activity: structuredClone(defaultDemoActivities[0]),
          trace_id: "tr_day0_start",
        } as StartSessionResponse;
      },
    );
  },

  startDayN(input: { memory_fixture_id: string; memory_bundle: null; topic_id: string; session_goal: string }): Promise<StartSessionResponse> {
    return withDemoFallback(
      () => request<any>("/api/v1/dayn/sessions", { method: "POST", body: JSON.stringify(input) }).then((raw) => normalizeStartSession(raw, input.memory_fixture_id)),
      () => {
        const learner = mockLearners.find((item) => item.learner_id === input.memory_fixture_id) ?? mockLearners[3];
        return {
          session_id: `demo-dayn-${learner.learner_id}`,
          mode: "dayn",
          next_activity: guidedActivity,
          trace_id: `tr_${learner.learner_id}_start`,
          learner,
          memory_preview: learner.memory_preview,
        };
      },
    );
  },

  submitTurn(sessionId: string, input: Record<string, unknown>, fallbackActivities: Activity[]): Promise<TurnResponse> {
    return withDemoFallback(
      () => request<any>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/turns`, { method: "POST", body: JSON.stringify(input) }).then((raw) => ({ ...raw, next_activity: normalizeActivity(raw.next_activity) })),
      () => {
        if (sessionId.includes("isha")) {
          return {
            turn_id: String(input.client_turn_id),
            outcome: "safe_refusal",
            feedback: [{ kind: "safety", text: "I don't have a verified explanation for that exact problem in this demo, so I won't invent one." }],
            next_activity: null,
            placement: null,
            why: "The requested topic is outside the pinned verified catalog.",
            memory: { event_id: "evt_safe_refusal", state_version: 1 },
            trace_id: "tr_isha_refusal",
          };
        }

        if (sessionId.includes("day0")) {
          const current = fallbackActivities[demoDay0Index];
          demoDay0Index += 1;
          const next = fallbackActivities[demoDay0Index];
          return {
            turn_id: String(input.client_turn_id),
            outcome: next ? "continue" : "placement_ready",
            feedback: [{ kind: "feedback", text: current?.kind === "numeric" ? "Good setup. You used net force before dividing by mass." : "Response recorded. I’ll use it with the rest of the diagnostic evidence." }],
            next_activity: next ?? null,
            placement: next ? null : {
              selected_strategy: "Guided Solver",
              modifiers: ["balanced"],
              observed: ["You identified net-force direction correctly.", "One structured hint helped on the acceleration step."],
              not_inferred: ["intelligence", "motivation", "permanent learning style"],
              certainty: "medium",
              next_evidence_needed: "Two independent problems will show when to reduce guidance.",
            },
            why: next ? "Building an initial plan from observable evidence." : "Enough useful evidence is available for a provisional starting strategy.",
            memory: { event_id: `evt_day0_${demoDay0Index}`, state_version: demoDay0Index + 1 },
            trace_id: `tr_day0_${demoDay0Index}`,
          };
        }

        return {
          turn_id: String(input.client_turn_id),
          outcome: "continue",
          feedback: [{ kind: "feedback", text: "Correct. Constant velocity means acceleration is zero, so the net force is zero." }],
          next_activity: { ...guidedActivity, activity_id: "n2l_guided_followup", eyebrow: "Guided practice", title: "A 4 kg box has 18 N right and 6 N left. What is its acceleration?" },
          placement: null,
          why: "A confirmed misconception was checked before the next guided problem.",
          memory: { event_id: "evt_kabir_025", state_version: 9 },
          trace_id: "tr_kabir_025",
        };
      },
    );
  },

  compare(input: Record<string, unknown>): Promise<CompareResponse> {
    return withDemoFallback(
      () => request<any>("/api/v1/compare", { method: "POST", body: JSON.stringify(input) }).then((raw) => ({
        left: {
          learner_id: raw.left.fixture.fixture_id,
          learner_name: raw.left.fixture.display_name,
          plan: raw.left.plan,
        },
        right: {
          learner_id: raw.right.fixture.fixture_id,
          learner_name: raw.right.fixture.display_name,
          plan: raw.right.plan,
        },
        differences: (raw.differences ?? []).map((item: any) => ({
          dimension: readable(item.dimension),
          left: Array.isArray(item.left) ? item.left.map(readable).join(" → ") : readable(item.left),
          right: Array.isArray(item.right) ? item.right.map(readable).join(" → ") : readable(item.right),
          reason: "Derived from the same goal with different learner evidence.",
        })),
      })),
      () => demoCompare,
    );
  },

  runEvaluation(): Promise<EvaluationResponse> {
    return withDemoFallback(
      () => request<any>("/api/v1/evaluations", { method: "POST", body: JSON.stringify({ repeat_runs: 20 }) }).then((raw) => ({
        status: raw.status,
        quality_score: raw.quality_score,
        gates: Object.entries(raw.hard_gates ?? {}).map(([name, passed]) => ({
          name: readable(name),
          passed: Boolean(passed),
          detail: passed ? "Required work-trial gate passed." : "Required work-trial gate failed.",
        })),
        cases: (raw.cases ?? []).map((item: any) => ({
          learner_id: item.fixture_id,
          expected: readable(item.expected_base_mode),
          actual: readable(item.actual_base_mode),
          passed: Boolean(item.policy_pass),
          plan_hash: item.plan_hashes?.[0],
          latency_ms: 0,
        })),
        honesty_notice: raw.honesty_notice,
      })),
      () => demoEvaluation,
    );
  },

  getTrace(traceId: string): Promise<ReviewerTrace> {
    return withDemoFallback(
      () => request<any>(`/api/v1/traces/${encodeURIComponent(traceId)}`).then(normalizeTrace),
      () => ({ ...demoTrace, trace_id: traceId }),
    );
  },
};
