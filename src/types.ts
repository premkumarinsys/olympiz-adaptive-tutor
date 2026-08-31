export type Outcome =
  | "continue"
  | "placement_ready"
  | "lesson_ready"
  | "clarification_required"
  | "safe_slowdown"
  | "safe_refusal"
  | "completed";

export type ConfidenceValue = 0.2 | 0.45 | 0.7 | 0.95;

export interface ActivityOption {
  id: string;
  label: string;
}

export interface Activity {
  activity_id: string;
  kind: "multiple_choice" | "numeric" | "short_text" | "explanation" | "reflection";
  eyebrow?: string;
  title?: string;
  prompt?: string;
  prompt_blocks?: string[];
  instructions?: string;
  options?: ActivityOption[];
  unit?: string;
  stage?: number;
  total_stages?: number;
}

export interface Placement {
  selected_strategy: string;
  modifiers: string[];
  observed: string[];
  not_inferred?: string[];
  certainty: "low" | "medium" | "high";
  next_evidence_needed: string;
}

export interface StartSessionResponse {
  session_id: string;
  mode: "day0" | "dayn";
  diagnostic_stage?: string;
  next_activity: Activity | null;
  trace_id: string;
  learner?: MockLearner;
  memory_preview?: MemoryPreview;
}

export interface TurnResponse {
  turn_id: string;
  outcome: Outcome;
  feedback: Array<{ kind: string; text: string }>;
  next_activity?: Activity | null;
  placement?: Placement | null;
  why?: string | null;
  memory?: { event_id: string; state_version: number };
  trace_id: string;
}

export interface MemoryPreview {
  summary: string;
  strengths: string[];
  needs_practice: string[];
  active_strategy: string;
  modifiers: string[];
  evidence_freshness: string;
  warning?: string;
}

export interface MockLearner {
  learner_id: string;
  name: string;
  scenario: string;
  exam_goal: string;
  base_mode: string;
  modifiers: string[];
  memory_preview: MemoryPreview;
}

export interface LessonBlock {
  order: number;
  kind: string;
  title?: string;
  content_ref?: { content_id: string; version: string };
  difficulty?: string | number;
  hint_limit?: number;
  decision_reason?: string;
}

export interface LessonPlan {
  plan_hash: string;
  input_hash?: string;
  policy_version: string;
  catalog_version: string;
  decision: {
    base_mode: string;
    modifiers: string[];
    provisional?: boolean;
    certainty?: string;
    reasons?: Array<Record<string, unknown>>;
  };
  blocks: LessonBlock[];
}

export interface CompareResponse {
  left: { learner_id: string; learner_name?: string; plan: LessonPlan };
  right: { learner_id: string; learner_name?: string; plan: LessonPlan };
  differences: Array<{
    dimension: string;
    left: string;
    right: string;
    reason?: string;
  }>;
}

export interface EvaluationCase {
  learner_id: string;
  expected: string;
  actual: string;
  passed: boolean;
  plan_hash?: string;
  latency_ms?: number;
}

export interface EvaluationResponse {
  status: "passed" | "failed";
  quality_score: number | null;
  gates: Array<{ name: string; passed: boolean; detail: string }>;
  cases: EvaluationCase[];
  honesty_notice: string;
}

export interface ReviewerTrace {
  trace_id: string;
  status: string;
  plan_hash: string;
  versions: Record<string, string>;
  pipeline: Array<{ name: string; status: "complete" | "blocked" | "fallback" }>;
  evidence: Array<{ observation: string; weight: string; use: string }>;
  rules: Array<{ id: string; detail: string; result: string }>;
  state_diff: Array<{ field: string; before: string; after: string }>;
  timings: Array<{ phase: string; ms: number }>;
}

export interface ApiErrorShape {
  code: string;
  message: string;
  retryable: boolean;
  trace_id?: string;
  details?: unknown;
}
