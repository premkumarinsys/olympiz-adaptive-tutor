import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowsClockwise,
  BookOpen,
  Brain,
  CaretDown,
  CaretRight,
  ChartBar,
  Check,
  CheckCircle,
  Circle,
  CircleNotch,
  Copy,
  Database,
  DownloadSimple,
  FileText,
  Flask,
  Gauge,
  GitDiff,
  GraduationCap,
  House,
  Info,
  Lightbulb,
  List,
  LockKey,
  Notebook,
  Pause,
  Play,
  ShieldCheck,
  Sparkle,
  Stack,
  Target,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import {
  BrowserRouter,
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { api, ApiError } from "./api";
import {
  confidenceChoices,
  defaultPlacement,
  demoActivities,
  demoCompare,
  demoEvaluation,
  demoTrace,
  guidedActivity,
  mockLearners,
} from "./demoData";
import type {
  Activity,
  CompareResponse,
  ConfidenceValue,
  EvaluationResponse,
  MockLearner,
  Placement,
  ReviewerTrace,
  StartSessionResponse,
  TurnResponse,
} from "./types";

type RouteState = {
  session?: StartSessionResponse;
  learner?: MockLearner;
  activity?: Activity;
  placement?: Placement;
  traceId?: string;
};

const readableMode = (value: string) =>
  value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

const getLearner = (id?: string) => mockLearners.find((learner) => learner.learner_id === id) ?? mockLearners[3];

function AppHeader({ name = "Kabir" }: { name?: string }) {
  const [notesOpen, setNotesOpen] = useState(false);
  const location = useLocation();
  const lessonRoute = location.pathname.includes("/lesson") || location.pathname.includes("/diagnostic");

  return (
    <header className="app-header">
      <Link className="brand" to="/" aria-label="Olympiz home">
        Olympiz
      </Link>
      <p className="welcome-copy">
        {lessonRoute ? (
          <>Welcome back, <strong>{name}</strong></>
        ) : (
          <>Adaptive tutoring, with every decision explained</>
        )}
      </p>
      <div className="header-actions">
        {!lessonRoute && (
          <Link className="header-home-link" to="/">
            <House size={20} aria-hidden="true" />
            <span>Home</span>
          </Link>
        )}
        <div className="notes-wrap">
          <button className="notes-button" type="button" onClick={() => setNotesOpen((open) => !open)} aria-expanded={notesOpen}>
            <Notebook size={22} aria-hidden="true" />
            <span>Notes</span>
          </button>
          {notesOpen && (
            <div className="notes-popover" role="dialog" aria-label="Session notes">
              <div className="popover-heading">
                <strong>Session notes</strong>
                <button type="button" className="icon-button" onClick={() => setNotesOpen(false)} aria-label="Close notes">
                  <X size={18} />
                </button>
              </div>
              <p>Your observations stay with this demo session.</p>
              <textarea aria-label="Write a private session note" placeholder="Write a quick note…" rows={4} />
              <button type="button" className="text-button" onClick={() => setNotesOpen(false)}>Save note</button>
            </div>
          )}
        </div>
        <button className="avatar-button" type="button" aria-label={`${name} account menu`}>
          <span>{name.slice(0, 1).toUpperCase()}</span>
          <CaretDown size={16} aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}

function Launcher() {
  const cards = [
    {
      to: "/day0/setup",
      icon: GraduationCap,
      title: "Meet a new learner",
      eyebrow: "Day 0",
      copy: "Run a short diagnostic and explain the provisional starting strategy.",
      cta: "Start diagnostic",
    },
    {
      to: "/dayn/select",
      icon: Brain,
      title: "Continue from memory",
      eyebrow: "Day N",
      copy: "Load a validated learner history and adapt the next lesson safely.",
      cta: "Choose a learner",
    },
    {
      to: "/compare",
      icon: GitDiff,
      title: "Compare two plans",
      eyebrow: "Reviewer demo",
      copy: "Lock the goal and see how evidence creates structural teaching differences.",
      cta: "Open comparison",
    },
    {
      to: "/eval",
      icon: Flask,
      title: "Run the evaluation",
      eyebrow: "Evidence",
      copy: "Check hard safety gates, golden policies, reproducibility, and latency.",
      cta: "View evaluation",
    },
  ];

  return (
    <div className="site-page">
      <AppHeader />
      <main className="launcher-main">
        <section className="launcher-hero" aria-labelledby="launcher-title">
          <div>
            <p className="section-kicker">Verified adaptive tutoring</p>
            <h1 id="launcher-title">Teach differently only when the evidence earns it.</h1>
            <p className="hero-copy">
              Olympiz turns observable learning evidence into a safe, inspectable lesson plan—without assigning permanent labels.
            </p>
          </div>
          <div className="hero-proof" aria-label="Prototype guarantees">
            <div><ShieldCheck size={25} /><span><strong>Verified content</strong>Physics claims stay pinned</span></div>
            <div><ArrowsClockwise size={25} /><span><strong>Reproducible plans</strong>Same inputs, same structure</span></div>
            <div><FileText size={25} /><span><strong>Decision trace</strong>Evidence maps to every change</span></div>
          </div>
        </section>

        <section className="launcher-grid" aria-label="Demo journeys">
          {cards.map(({ to, icon: Icon, title, eyebrow, copy, cta }) => (
            <Link className="journey-card" to={to} key={to}>
              <span className="journey-icon"><Icon size={26} weight="regular" /></span>
              <span className="card-kicker">{eyebrow}</span>
              <h2>{title}</h2>
              <p>{copy}</p>
              <span className="card-link">{cta}<ArrowRight size={18} /></span>
            </Link>
          ))}
        </section>

        <section className="scope-band">
          <div><strong>Prototype domain</strong><span>Newton’s laws</span></div>
          <div><strong>Policy</strong><span>2026-08-28.2</span></div>
          <div><strong>Catalog</strong><span>mechanics-2026-08-28</span></div>
          <div><strong>Orchestration</strong><span>Bounded LangGraph</span></div>
          <div><strong>Renderer</strong><span>LLM + verified fallback</span></div>
          <Link to="/about-design">How the system works <CaretRight size={17} /></Link>
        </section>
      </main>
    </div>
  );
}

function PageIntro({ kicker, title, copy, backTo = "/" }: { kicker: string; title: string; copy: string; backTo?: string }) {
  return (
    <div className="page-intro">
      <Link to={backTo} className="back-link"><ArrowLeft size={18} />Back</Link>
      <p className="section-kicker">{kicker}</p>
      <h1>{title}</h1>
      <p>{copy}</p>
    </div>
  );
}

function Day0SetupPage() {
  const navigate = useNavigate();
  const [goal, setGoal] = useState("JEE Main");
  const [language, setLanguage] = useState("en");
  const [pace, setPace] = useState("careful");
  const [readingDensity, setReadingDensity] = useState("standard");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function startDiagnostic(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const session = await api.startDay0({
        learner_id: `demo-new-${Date.now()}`,
        exam_goal: goal,
        topic_id: "newton_second_law",
        language,
        accessibility: readingDensity === "standard" ? [] : [`reading_density:${readingDensity}`],
        pace_preference: pace,
        idempotency_key: crypto.randomUUID(),
      });
      const activity = session.next_activity?.activity_id ? session.next_activity : demoActivities[0];
      navigate(`/day0/${session.session_id}/diagnostic`, { state: { session, activity, traceId: session.trace_id } satisfies RouteState });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start the diagnostic.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="site-page">
      <AppHeader name="New learner" />
      <main className="form-page">
        <PageIntro kicker="Day 0 · 8–12 minutes" title="Build an initial plan together" copy="A short diagnostic checks prerequisites, independent reasoning, response to one hint, and confidence. The result stays provisional." />
        <form className="setup-card" onSubmit={startDiagnostic}>
          <div className="form-heading">
            <span className="step-chip">1</span>
            <div><h2>Set the learning goal</h2><p>These are explicit preferences, not inferred traits.</p></div>
          </div>
          <label>
            Exam goal
            <select value={goal} onChange={(event) => setGoal(event.target.value)}>
              <option>NEET</option>
              <option>JEE Main</option>
              <option>JEE Advanced</option>
              <option>Olympiad</option>
              <option>Exploring</option>
            </select>
          </label>
          <label>
            Topic
            <input value="Newton’s laws" disabled aria-describedby="topic-help" />
            <small id="topic-help">The verified prototype catalog is intentionally narrow.</small>
          </label>
          <div className="field-grid">
            <label>
              Language
              <select value={language} onChange={(event) => setLanguage(event.target.value)}>
                <option value="en">English</option>
                <option value="hi" disabled>Hindi — not in this demo</option>
              </select>
            </label>
            <label>
              Session pace
              <select value={pace} onChange={(event) => setPace(event.target.value)}>
                <option value="careful">Careful start</option>
                <option value="quick">Quick start</option>
              </select>
            </label>
          </div>
          <fieldset className="segmented-fieldset">
            <legend>Reading density</legend>
            <div className="segment-options">
              {["standard", "spacious", "compact"].map((value) => (
                <label key={value} className={readingDensity === value ? "selected" : ""}>
                  <input type="radio" name="density" value={value} checked={readingDensity === value} onChange={() => setReadingDensity(value)} />
                  {readableMode(value)}
                </label>
              ))}
            </div>
          </fieldset>
          {error && <InlineError message={error} />}
          <div className="form-actions">
            <p><LockKey size={17} />Only mock learner data is used in this prototype.</p>
            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? <CircleNotch className="spin" size={20} /> : <Play size={20} weight="fill" />}
              {submitting ? "Starting…" : "Start diagnostic"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}

function LearningSidebar({
  learner,
  goal = "Apply net force before F = ma",
  compact = false,
}: {
  learner: MockLearner;
  goal?: string;
  compact?: boolean;
}) {
  return (
    <aside className={`learning-sidebar${compact ? " compact" : ""}`} aria-label="Learning context">
      <section>
        <h2><Target size={28} weight="regular" />Today’s goal</h2>
        <p className="goal-copy">{goal}</p>
        <button type="button" className="rail-link">View goal breakdown<CaretRight size={18} /></button>
      </section>
      <section>
        <h2><Brain size={28} weight="regular" />What I remember</h2>
        <h3>Strong</h3>
        <ul className="memory-list strong-list">
          {learner.memory_preview.strengths.slice(0, 2).map((item) => <li key={item}><CheckCircle size={21} weight="fill" />{item}</li>)}
        </ul>
        <h3 className="needs-label">Needs practice</h3>
        <ul className="memory-list needs-list">
          {learner.memory_preview.needs_practice.slice(0, 2).map((item) => <li key={item}><Circle size={18} weight="fill" />{item}</li>)}
        </ul>
        <button type="button" className="rail-link">Review all ({learner.memory_preview.strengths.length + learner.memory_preview.needs_practice.length})<CaretRight size={18} /></button>
      </section>
      {!compact && (
        <div className="streak-card">
          <Gauge size={27} />
          <span><strong>Evidence status</strong>{learner.memory_preview.evidence_freshness}</span>
        </div>
      )}
    </aside>
  );
}

function ProgressPath({ active = 2 }: { active?: number }) {
  const steps = [
    { title: "Explain", status: active > 1 ? "Done" : "In progress" },
    { title: "Try", status: active === 2 ? "In progress" : active > 2 ? "Done" : "Upcoming" },
    { title: "Check", status: active === 3 ? "In progress" : active > 3 ? "Done" : "Upcoming" },
    { title: "Reflect", status: active === 4 ? "In progress" : "Upcoming" },
  ];
  return (
    <nav className="progress-path" aria-label="Lesson stages">
      {steps.map((step, index) => {
        const number = index + 1;
        const complete = active > number;
        const current = active === number;
        return (
          <div className={`progress-step${current ? " current" : ""}${complete ? " complete" : ""}`} key={step.title} aria-current={current ? "step" : undefined}>
            <span className="progress-marker">{complete ? <Check size={21} weight="bold" /> : number}</span>
            <span><strong>{step.title}</strong><small>{step.status}</small></span>
          </div>
        );
      })}
    </nav>
  );
}

function AnswerActivity({
  activity,
  submitting,
  feedback,
  onSubmit,
  onCounterexample,
}: {
  activity: Activity;
  submitting: boolean;
  feedback?: string;
  onSubmit: (answer: string, confidence: ConfidenceValue) => void;
  onCounterexample?: () => void;
}) {
  const [answer, setAnswer] = useState("");
  const [confidence, setConfidence] = useState<ConfidenceValue | null>(null);
  const [validation, setValidation] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const answerGroupId = useId();

  useEffect(() => {
    setAnswer("");
    setConfidence(null);
    setValidation("");
    headingRef.current?.focus();
  }, [activity.activity_id]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!answer || confidence === null) {
      setValidation("Choose an answer and confidence level before continuing.");
      return;
    }
    setValidation("");
    onSubmit(answer, confidence);
  }

  return (
    <form className="activity-card" onSubmit={submit}>
      <p className="activity-eyebrow">{activity.eyebrow ?? "Try it"}</p>
      <h1 ref={headingRef} tabIndex={-1}>{activity.title ?? activity.prompt ?? "Continue the lesson"}</h1>
      <p className="activity-instruction">{activity.instructions ?? "Respond using the information in the prompt."}</p>

      {activity.kind === "multiple_choice" ? (
        <fieldset className="answer-options" aria-describedby={`${answerGroupId}-instruction`}>
          <legend className="sr-only">Answer choices</legend>
          <span className="sr-only" id={`${answerGroupId}-instruction`}>Choose one answer.</span>
          {(activity.options ?? []).map((option) => (
            <label key={option.id} className={answer === option.id ? "selected" : ""}>
              <input type="radio" name={answerGroupId} value={option.id} checked={answer === option.id} onChange={() => setAnswer(option.id)} />
              <span className="radio-mark" aria-hidden="true" />
              <span>{option.label}</span>
            </label>
          ))}
        </fieldset>
      ) : (
        <label className="numeric-answer">
          Your answer
          <span><input inputMode={activity.kind === "numeric" ? "decimal" : "text"} value={answer} onChange={(event) => setAnswer(event.target.value)} />{activity.unit && <strong>{activity.unit}</strong>}</span>
        </label>
      )}

      <fieldset className="confidence-fieldset">
        <legend>How confident are you?</legend>
        <div className="confidence-options">
          {confidenceChoices.map((choice) => (
            <label key={choice.value} className={confidence === choice.value ? "selected" : ""}>
              <input type="radio" name={`${answerGroupId}-confidence`} checked={confidence === choice.value} onChange={() => setConfidence(choice.value)} />
              <span className="radio-mark" aria-hidden="true" />
              <span>{choice.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {validation && <p className="field-error" role="alert"><WarningCircle size={18} />{validation}</p>}
      {feedback && <div className="feedback-message" role="status"><CheckCircle size={21} weight="fill" /><span>{feedback}</span></div>}

      <div className="activity-actions">
        <button className="primary-button" type="submit" disabled={submitting || Boolean(feedback)}>
          {submitting ? <CircleNotch className="spin" size={20} /> : null}
          {submitting ? "Checking…" : "Check my reasoning"}
          {!submitting && <ArrowRight size={21} />}
        </button>
        {onCounterexample && (
          <button className="secondary-button" type="button" onClick={onCounterexample}>
            Show a counterexample
          </button>
        )}
      </div>
      <p className="activity-footnote">We’ll check your reasoning and adapt what comes next.</p>
    </form>
  );
}

function LearningNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="learning-notice">
      <WarningCircle size={26} weight="regular" />
      <p>{children}</p>
      <button type="button" className="notice-link">Learn more</button>
    </div>
  );
}

function SessionSummary({ onTrace, traceOpen }: { onTrace: () => void; traceOpen: boolean }) {
  return (
    <footer className="session-summary" aria-label="Session summary">
      <div><Sparkle size={27} /><span><strong>Guided Solver</strong><small>Work step-by-step with hints</small></span></div>
      <div><Lightbulb size={28} /><span><strong>2 hints available</strong><small>Use when you’re stuck</small></span></div>
      <button type="button" onClick={onTrace} aria-expanded={traceOpen}>
        <FileText size={27} /><span><strong>Decision trace</strong><small>See why Olympiz adapts</small></span><CaretDown className={traceOpen ? "rotate" : ""} size={18} />
      </button>
      <div><ShieldCheck size={31} /><span><strong>Verified content</strong><small>Aligned to JEE/NEET syllabus</small></span></div>
    </footer>
  );
}

function ReviewerDrawer({ open, onClose, traceId }: { open: boolean; onClose: () => void; traceId: string }) {
  const [trace, setTrace] = useState<ReviewerTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || trace) return;
    setLoading(true);
    api.getTrace(traceId || demoTrace.trace_id)
      .then(setTrace)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Trace unavailable."))
      .finally(() => setLoading(false));
  }, [open, trace, traceId]);

  if (!open) return null;
  const shownTrace = trace ?? demoTrace;

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="reviewer-drawer" role="dialog" aria-modal="true" aria-labelledby="trace-title">
        <header>
          <div><p className="section-kicker">Reviewer view</p><h2 id="trace-title">Decision trace</h2></div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close decision trace"><X size={22} /></button>
        </header>
        <div className="trace-notice"><Info size={19} /><span>Recorded evidence and deterministic rules—not private model reasoning.</span></div>
        {loading ? <LoadingBlock label="Loading trace" /> : error ? <InlineError message={error} /> : (
          <div className="trace-content">
            <section className="trace-overview">
              <span className="status-pill success"><CheckCircle size={16} weight="fill" />Validated</span>
              <dl>
                <div><dt>Trace ID</dt><dd>{shownTrace.trace_id}</dd></div>
                <div><dt>Plan hash</dt><dd>{shownTrace.plan_hash}</dd></div>
              </dl>
              <div className="trace-actions">
                <button type="button" onClick={() => navigator.clipboard?.writeText(shownTrace.plan_hash)}><Copy size={17} />Copy hash</button>
                <button type="button"><DownloadSimple size={17} />Trace JSON</button>
              </div>
            </section>
            <section><h3>Pipeline</h3><div className="pipeline-list">{shownTrace.pipeline.map((item) => <span key={item.name} className={item.status}><Check size={14} />{item.name}</span>)}</div></section>
            <section><h3>Evidence used</h3><div className="trace-list">{shownTrace.evidence.map((item) => <div key={item.observation}><strong>{item.observation}</strong><span>{item.weight}</span><p>{item.use}</p></div>)}</div></section>
            <section><h3>Rules fired</h3><div className="trace-list">{shownTrace.rules.map((item) => <div key={item.id}><code>{item.id}</code><strong>{item.result}</strong><p>{item.detail}</p></div>)}</div></section>
            <section><h3>State change</h3><div className="state-diff">{shownTrace.state_diff.map((item) => <div key={item.field}><code>{item.field}</code><span>{item.before}</span><ArrowRight size={15} /><strong>{item.after}</strong></div>)}</div></section>
          </div>
        )}
      </aside>
    </div>
  );
}

function LessonWorkspace({
  learner,
  activity,
  sessionId,
  initialTraceId,
  diagnostic = false,
}: {
  learner: MockLearner;
  activity: Activity;
  sessionId: string;
  initialTraceId: string;
  diagnostic?: boolean;
}) {
  const navigate = useNavigate();
  const [current, setCurrent] = useState(activity);
  const [pendingNext, setPendingNext] = useState<Activity | null>(null);
  const [feedback, setFeedback] = useState("");
  const [turnResult, setTurnResult] = useState<TurnResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [traceOpen, setTraceOpen] = useState(false);
  const [traceId, setTraceId] = useState(initialTraceId);
  const [counterexample, setCounterexample] = useState(false);
  const startedAt = useRef(performance.now());
  const pendingTurnId = useRef<string | null>(null);

  async function submit(answer: string, confidence: ConfidenceValue) {
    setSubmitting(true);
    setError("");
    pendingTurnId.current ??= crypto.randomUUID();
    try {
      const result = await api.submitTurn(sessionId, {
        client_turn_id: pendingTurnId.current,
        activity_id: current.activity_id,
        response: { kind: current.kind === "multiple_choice" ? "choice" : current.kind, value: answer },
        confidence,
        elapsed_ms: Math.round(performance.now() - startedAt.current),
        requested_hint_ids: counterexample ? ["counterexample_01"] : [],
      }, demoActivities);
      pendingTurnId.current = null;
      setTurnResult(result);
      setTraceId(result.trace_id);
      setFeedback(result.feedback?.map((item) => item.text).join(" ") || "Response recorded.");
      setPendingNext(result.next_activity?.activity_id ? result.next_activity : null);
    } catch (reason) {
      const message = reason instanceof ApiError ? reason.message : "We could not save this turn.";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  function continueLesson() {
    if (turnResult?.outcome === "placement_ready") {
      navigate(`/day0/${sessionId}/placement`, { state: { placement: turnResult.placement ?? defaultPlacement, traceId } satisfies RouteState });
      return;
    }
    if (turnResult?.outcome === "safe_refusal") return;
    if (pendingNext) {
      setCurrent(pendingNext);
      setPendingNext(null);
      setFeedback("");
      setTurnResult(null);
      setCounterexample(false);
      startedAt.current = performance.now();
    }
  }

  const stage = diagnostic ? Math.min(current.stage ?? 2, 4) : 2;
  const refusal = turnResult?.outcome === "safe_refusal";

  return (
    <div className="lesson-screen">
      <AppHeader name={learner.name} />
      <div className="lesson-layout">
        <LearningSidebar learner={learner} goal={diagnostic ? "Find a safe starting point for Newton’s laws" : undefined} />
        <main className="lesson-main">
          <ProgressPath active={stage} />
          <div className="lesson-scroll">
            <LearningNotice>
              {diagnostic
                ? "I’m using these questions to build an early plan, not to give you a score."
                : "I’m checking this idea first because it appeared in two recent answers."}
            </LearningNotice>
            {counterexample && (
              <div className="counterexample-panel" role="status">
                <Lightbulb size={22} />
                <div><strong>Counterexample</strong><p>A puck gliding with negligible friction keeps moving even after the push ends. Motion can continue while net force is zero.</p></div>
              </div>
            )}
            {refusal ? (
              <SafeRefusal why={turnResult?.why ?? "Verified content is unavailable."} />
            ) : (
              <AnswerActivity activity={current} submitting={submitting} feedback={feedback} onSubmit={submit} onCounterexample={() => setCounterexample(true)} />
            )}
            {error && <InlineError message={error} actionLabel="Try again" onAction={() => setError("")} />}
            {feedback && !refusal && (
              <div className="continue-row">
                <button type="button" className="primary-button" onClick={continueLesson}>
                  {turnResult?.outcome === "placement_ready" ? "See my starting plan" : "Continue"}<ArrowRight size={20} />
                </button>
              </div>
            )}
          </div>
        </main>
      </div>
      <SessionSummary onTrace={() => setTraceOpen(true)} traceOpen={traceOpen} />
      <ReviewerDrawer open={traceOpen} onClose={() => setTraceOpen(false)} traceId={traceId} />
    </div>
  );
}

function Day0DiagnosticPage() {
  const { sessionId = "demo-day0" } = useParams();
  const location = useLocation();
  const state = (location.state ?? {}) as RouteState;
  const learner: MockLearner = {
    ...mockLearners[3],
    learner_id: "new-learner",
    name: "Prem",
    memory_preview: {
      summary: "Building an initial evidence-based plan.",
      strengths: ["No stable evidence yet"],
      needs_practice: ["Collecting prerequisite evidence"],
      active_strategy: "Provisional Guided Solver",
      modifiers: ["balanced"],
      evidence_freshness: "New diagnostic",
    },
  };
  return <LessonWorkspace learner={learner} activity={state.activity ?? state.session?.next_activity ?? demoActivities[0]} sessionId={sessionId} initialTraceId={state.traceId ?? "tr_day0_start"} diagnostic />;
}

function PlacementPage() {
  const { sessionId = "demo-day0" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state ?? {}) as RouteState;
  const placement = state.placement ?? defaultPlacement;
  const [traceOpen, setTraceOpen] = useState(false);

  return (
    <div className="site-page placement-page">
      <AppHeader name="Prem" />
      <main>
        <section className="placement-card">
          <span className="placement-icon"><Sparkle size={30} /></span>
          <p className="section-kicker">Your starting plan</p>
          <h1>We’ll begin with {readableMode(placement.selected_strategy).toLowerCase()}.</h1>
          <p className="placement-summary">This is an early estimate. It can change when new independent evidence becomes available.</p>
          <div className="certainty-row"><span>Estimate certainty</span><strong>{readableMode(placement.certainty)}</strong><div className={`certainty-meter ${placement.certainty}`}><span /></div></div>
          <section className="observed-section">
            <h2>What I observed</h2>
            <ul>{placement.observed.map((item) => <li key={item}><CheckCircle size={20} weight="fill" />{item}</li>)}</ul>
          </section>
          <section className="next-evidence"><Info size={21} /><div><strong>What I’ll watch next</strong><p>{placement.next_evidence_needed}</p></div></section>
          <div className="placement-actions">
            <button type="button" className="primary-button" onClick={() => navigate(`/day0/${sessionId}/lesson`, { state: { learner: mockLearners[3], activity: guidedActivity, traceId: state.traceId } satisfies RouteState })}>Begin first lesson<ArrowRight size={20} /></button>
            <button type="button" className="secondary-button">Change pace or format</button>
            <button type="button" className="text-button" onClick={() => setTraceOpen(true)}>Open decision trace</button>
          </div>
        </section>
        <p className="placement-boundary"><ShieldCheck size={18} />We did not infer intelligence, motivation, personality, or a permanent learning style.</p>
      </main>
      <ReviewerDrawer open={traceOpen} onClose={() => setTraceOpen(false)} traceId={state.traceId ?? "tr_day0_placement"} />
    </div>
  );
}

function Day0LessonPage() {
  const { sessionId = "demo-day0-lesson" } = useParams();
  const location = useLocation();
  const state = (location.state ?? {}) as RouteState;
  return <LessonWorkspace learner={state.learner ?? mockLearners[3]} activity={state.activity ?? guidedActivity} sessionId={sessionId} initialTraceId={state.traceId ?? "tr_day0_lesson"} />;
}

function ProfileSelectPage() {
  const [learners, setLearners] = useState<MockLearner[]>(mockLearners);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getMockLearners().then((data) => Array.isArray(data) && data.length && setLearners(data)).catch((reason) => setError(reason.message)).finally(() => setLoading(false));
  }, []);

  return (
    <div className="site-page">
      <AppHeader />
      <main className="profiles-page">
        <PageIntro kicker="Day N" title="Choose a learner memory" copy="Each profile passes through the same reducer, policy, retriever, and planner. The UI does not hard-code the lesson decision." />
        {loading && <LoadingBlock label="Loading learner memories" />}
        {error && <InlineError message={error} />}
        <div className="profile-grid">
          {learners.map((learner) => (
            <Link className={`profile-card${learner.learner_id === "isha" ? " safety" : ""}`} to={`/dayn/${learner.learner_id}/preview`} key={learner.learner_id} state={{ learner } satisfies RouteState}>
              <div className="profile-avatar">{learner.name.slice(0, 1)}</div>
              <div className="profile-heading"><span>{learner.exam_goal}</span><h2>{learner.name}</h2></div>
              <p>{learner.scenario}</p>
              <div className="strategy-row"><strong>{learner.base_mode}</strong>{learner.modifiers.map((modifier) => <span key={modifier}>{modifier}</span>)}</div>
              <span className="card-link">Preview memory<CaretRight size={18} /></span>
            </Link>
          ))}
        </div>
      </main>
    </div>
  );
}

function MemoryPreviewPage() {
  const { learnerId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const state = (location.state ?? {}) as RouteState;
  const learner = state.learner ?? getLearner(learnerId);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  async function begin() {
    setStarting(true);
    setError("");
    try {
      const session = await api.startDayN({ memory_fixture_id: learner.learner_id, memory_bundle: null, topic_id: "newton_second_law", session_goal: "practice" });
      navigate(`/dayn/${session.session_id}/lesson`, { state: { session, learner, activity: session.next_activity, traceId: session.trace_id } satisfies RouteState });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load this memory.");
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="site-page">
      <AppHeader name={learner.name} />
      <main className="memory-preview-page">
        <PageIntro kicker="Validated learner memory" title={`Welcome back, ${learner.name}`} copy={learner.memory_preview.summary} backTo="/dayn/select" />
        {learner.memory_preview.warning && <div className="memory-warning"><WarningCircle size={23} /><span>{learner.memory_preview.warning}</span></div>}
        <div className="memory-preview-grid">
          <section className="memory-panel">
            <h2><Brain size={23} />Current evidence</h2>
            <div className="memory-columns">
              <div><h3>Strong</h3><ul>{learner.memory_preview.strengths.map((item) => <li key={item}><CheckCircle size={19} weight="fill" />{item}</li>)}</ul></div>
              <div><h3 className="needs-label">Needs practice</h3><ul>{learner.memory_preview.needs_practice.map((item) => <li key={item}><Circle size={16} weight="fill" />{item}</li>)}</ul></div>
            </div>
            <p className="freshness"><ArrowsClockwise size={18} />{learner.memory_preview.evidence_freshness}</p>
          </section>
          <section className="strategy-panel">
            <p className="section-kicker">How we’ll start</p>
            <h2>{learner.memory_preview.active_strategy}</h2>
            <div className="modifier-list">{learner.memory_preview.modifiers.length ? learner.memory_preview.modifiers.map((item) => <span key={item}>{item}</span>) : <span>verified-content gate</span>}</div>
            <p>The base strategy stays locked for this session. Hints and smaller chunks can still change tactically.</p>
            <button type="button" className="text-button">This does not look right</button>
          </section>
        </div>
        {error && <InlineError message={error} />}
        <div className="preview-actions">
          <button type="button" className="primary-button" onClick={begin} disabled={starting}>{starting ? <CircleNotch className="spin" size={20} /> : <Play size={20} weight="fill" />}{starting ? "Loading memory…" : "Begin lesson"}</button>
          <Link className="secondary-button as-link" to="/compare">Compare with another learner</Link>
        </div>
      </main>
    </div>
  );
}

function DayNLessonPage() {
  const { sessionId = "demo-dayn-kabir" } = useParams();
  const location = useLocation();
  const state = (location.state ?? {}) as RouteState;
  const idFromSession = sessionId.split("-").at(-1);
  const learner = state.learner ?? getLearner(idFromSession);
  return <LessonWorkspace learner={learner} activity={state.activity ?? state.session?.next_activity ?? guidedActivity} sessionId={sessionId} initialTraceId={state.traceId ?? `tr_${learner.learner_id}_start`} />;
}

function PlanTimeline({ side, name, plan }: { side: "left" | "right"; name: string; plan: CompareResponse["left"]["plan"] }) {
  return (
    <section className={`plan-column ${side}`}>
      <header>
        <span className="plan-avatar">{name.slice(0, 1)}</span>
        <div><p>{name}</p><h2>{readableMode(plan.decision.base_mode)}</h2></div>
      </header>
      <div className="plan-modifiers">{plan.decision.modifiers.map((item) => <span key={item}>{readableMode(item)}</span>)}</div>
      <ol className="timeline">
        {plan.blocks.map((block) => (
          <li key={`${block.order}-${block.kind}`}>
            <span>{block.order}</span>
            <div><small>{readableMode(block.kind)}</small><strong>{block.title ?? readableMode(block.kind)}</strong>{block.hint_limit !== undefined && <p>{block.hint_limit} hint{block.hint_limit === 1 ? "" : "s"} available</p>}</div>
          </li>
        ))}
      </ol>
      <footer><span>Plan hash</span><code>{plan.plan_hash}</code></footer>
    </section>
  );
}

function ComparePage() {
  const [leftId, setLeftId] = useState("asha");
  const [rightId, setRightId] = useState("meera");
  const [result, setResult] = useState<CompareResponse | null>(demoCompare);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function compare() {
    if (leftId === rightId) {
      setError("Choose two different learners, or use the repeat-run control for a determinism check.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      setResult(await api.compare({ left_learner_id: leftId, right_learner_id: rightId, topic_id: "newton_second_law", objective_id: "apply_f_equals_ma", dry_run: true }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Comparison failed.");
    } finally {
      setLoading(false);
    }
  }

  const shown = result ?? demoCompare;
  return (
    <div className="site-page">
      <AppHeader />
      <main className="compare-page">
        <PageIntro kicker="Reviewer demo" title="Same goal. Different teaching structure." copy="The concept, objective, catalog, and policy version stay locked. Only learner evidence changes." />
        <section className="compare-controls">
          <label>Learner A<select value={leftId} onChange={(event) => setLeftId(event.target.value)}>{mockLearners.map((learner) => <option value={learner.learner_id} key={learner.learner_id}>{learner.name}</option>)}</select></label>
          <label>Learner B<select value={rightId} onChange={(event) => setRightId(event.target.value)}>{mockLearners.map((learner) => <option value={learner.learner_id} key={learner.learner_id}>{learner.name}</option>)}</select></label>
          <div className="locked-objective"><LockKey size={19} /><span><strong>Locked objective</strong>Calculate acceleration from multiple horizontal forces</span></div>
          <button type="button" className="primary-button" onClick={compare} disabled={loading}>{loading ? <CircleNotch className="spin" size={20} /> : <GitDiff size={20} />}{loading ? "Generating…" : "Generate both plans"}</button>
        </section>
        {error && <InlineError message={error} />}
        <div className="compare-grid">
          <PlanTimeline side="left" name={shown.left.learner_name ?? readableMode(shown.left.learner_id)} plan={shown.left.plan} />
          <PlanTimeline side="right" name={shown.right.learner_name ?? readableMode(shown.right.learner_id)} plan={shown.right.plan} />
        </div>
        <section className="diff-section">
          <div className="section-heading-row"><div><p className="section-kicker">Structural diff</p><h2>Why the plans differ</h2></div><button type="button" className="secondary-button"><ArrowsClockwise size={18} />Repeat run</button></div>
          <div className="diff-table" role="table" aria-label="Plan differences">
            <div className="diff-header" role="row"><span role="columnheader">Dimension</span><span role="columnheader">Asha</span><span role="columnheader">Meera</span><span role="columnheader">Evidence</span></div>
            {shown.differences.map((difference) => <div className="diff-row" role="row" key={difference.dimension}><strong role="cell">{difference.dimension}</strong><span role="cell">{difference.left}</span><span role="cell">{difference.right}</span><small role="cell">{difference.reason}</small></div>)}
          </div>
        </section>
      </main>
    </div>
  );
}

function EvaluationPage() {
  const [report, setReport] = useState<EvaluationResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setRunning(true);
    setError("");
    try {
      setReport(await api.runEvaluation());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Evaluation failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="site-page">
      <AppHeader />
      <main className="evaluation-page">
        <PageIntro kicker="Evaluation" title="Safety gates before quality scores" copy="A green score is shown only after every non-compensable gate passes." />
        <div className="evaluation-toolbar">
          <div className={`run-status ${report ? report.status : "not-run"}`}><span>{report ? (report.status === "passed" ? <CheckCircle size={23} weight="fill" /> : <WarningCircle size={23} />) : <Pause size={23} />}</span><div><strong>{report ? readableMode(report.status) : "Not run"}</strong><small>{report ? "Golden suite completed" : "Run the fixed local cases"}</small></div></div>
          <button type="button" className="primary-button" onClick={run} disabled={running}>{running ? <CircleNotch className="spin" size={20} /> : <Play size={19} weight="fill" />}{running ? "Running suite…" : report ? "Run again" : "Run evaluation"}</button>
        </div>
        {error && <InlineError message={error} />}
        {!report ? (
          <section className="empty-evaluation"><Flask size={42} /><h2>No results yet</h2><p>Nothing is marked successful until the suite actually runs.</p></section>
        ) : (
          <>
            <section className="gates-section">
              <div className="section-heading-row"><div><p className="section-kicker">Release gates</p><h2>{report.gates.filter((gate) => gate.passed).length} of {report.gates.length} passed</h2></div>{report.quality_score !== null && <div className="score-badge"><strong>{report.quality_score}</strong><span>Quality score</span></div>}</div>
              <div className="gate-grid">{report.gates.map((gate) => <article key={gate.name} className={gate.passed ? "passed" : "failed"}>{gate.passed ? <CheckCircle size={23} weight="fill" /> : <WarningCircle size={23} />}<div><h3>{gate.name}</h3><p>{gate.detail}</p></div></article>)}</div>
            </section>
            <section className="golden-section">
              <div className="section-heading-row"><div><p className="section-kicker">Golden profiles</p><h2>Expected versus actual</h2></div><button className="secondary-button" type="button"><DownloadSimple size={18} />Export JSON</button></div>
              <div className="golden-table" role="table" aria-label="Golden profile results">
                <div className="golden-header" role="row"><span role="columnheader">Learner</span><span role="columnheader">Expected policy</span><span role="columnheader">Actual policy</span><span role="columnheader">Result</span><span role="columnheader">Latency</span></div>
                {report.cases.map((item) => <div className="golden-row" role="row" key={item.learner_id}><strong role="cell">{readableMode(item.learner_id)}</strong><span role="cell">{item.expected}</span><span role="cell">{item.actual}</span><span role="cell" className={item.passed ? "pass-cell" : "fail-cell"}>{item.passed ? <CheckCircle size={17} weight="fill" /> : <WarningCircle size={17} />}{item.passed ? "Pass" : "Fail"}</span><small role="cell">{item.latency_ms} ms</small></div>)}
              </div>
            </section>
            <div className="honesty-notice"><Info size={21} /><p>{report.honesty_notice}</p></div>
          </>
        )}
      </main>
    </div>
  );
}

function AboutDesignPage() {
  const stages = [
    { icon: Database, title: "Evidence", copy: "Immutable observations are folded into bounded learner state." },
    { icon: Gauge, title: "Policy", copy: "Versioned rules choose a base lesson mode and controlled modifiers." },
    { icon: Stack, title: "Verified content", copy: "Deterministic retrieval selects only approved claims and activities." },
    { icon: ArrowsClockwise, title: "Agent graph", copy: "LangGraph runs one explicit, inspectable path for each learner turn." },
    { icon: Sparkle, title: "LLM response", copy: "One optional model call turns the approved plan into concise teaching language." },
    { icon: ShieldCheck, title: "Validate + fallback", copy: "Unknown claims or model failures switch to the verified template renderer." },
  ];
  return (
    <div className="site-page">
      <AppHeader />
      <main className="about-page">
        <PageIntro kicker="System design" title="A learner observation should lead to a visible, reproducible teaching change." copy="A bounded LangGraph loop coordinates the turn. The language model may phrase approved content, but it cannot choose teaching policy, grade answers, invent physics, or write learner memory." />
        <div className="system-flow">{stages.map(({ icon: Icon, title, copy }, index) => <article key={title}><span><Icon size={25} /></span><small>0{index + 1}</small><h2>{title}</h2><p>{copy}</p></article>)}</div>
        <section className="principles-grid">
          <article><ShieldCheck size={25} /><h2>Correctness is a gate</h2><p>An unsupported answer becomes a safe refusal, not a creative guess.</p></article>
          <article><ArrowsClockwise size={25} /><h2>Memory is reversible</h2><p>Raw observations remain immutable while derived beliefs can be revised or retired.</p></article>
          <article><FileText size={25} /><h2>Explanations use evidence</h2><p>Reviewer traces show rule IDs, thresholds, versions, and actions—never hidden reasoning.</p></article>
        </section>
      </main>
    </div>
  );
}

function SafeRefusal({ why }: { why: string }) {
  return (
    <section className="safe-refusal" role="status">
      <span><ShieldCheck size={33} /></span>
      <p className="section-kicker">Verified-content boundary</p>
      <h1>I won’t invent an explanation.</h1>
      <p>I don’t have a verified explanation for that exact problem in this demo. I can review a supported prerequisite or mark the topic for a content reviewer.</p>
      <div><Info size={19} /><span>{why}</span></div>
      <div className="activity-actions"><button type="button" className="primary-button">Review net force<ArrowRight size={19} /></button><Link className="secondary-button as-link" to="/dayn/select">Choose another learner</Link></div>
    </section>
  );
}

function LoadingBlock({ label }: { label: string }) {
  return <div className="loading-block" role="status"><CircleNotch className="spin" size={23} /><span>{label}</span></div>;
}

function InlineError({ message, actionLabel, onAction }: { message: string; actionLabel?: string; onAction?: () => void }) {
  return <div className="inline-error" role="alert"><WarningCircle size={21} /><span>{message}</span>{actionLabel && onAction && <button type="button" onClick={onAction}>{actionLabel}</button>}</div>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Launcher />} />
      <Route path="/day0" element={<Navigate to="/day0/setup" replace />} />
      <Route path="/day0/setup" element={<Day0SetupPage />} />
      <Route path="/day0/:sessionId/diagnostic" element={<Day0DiagnosticPage />} />
      <Route path="/day0/:sessionId/placement" element={<PlacementPage />} />
      <Route path="/day0/:sessionId/lesson" element={<Day0LessonPage />} />
      <Route path="/dayn" element={<Navigate to="/dayn/select" replace />} />
      <Route path="/dayn/select" element={<ProfileSelectPage />} />
      <Route path="/dayn/:learnerId/preview" element={<MemoryPreviewPage />} />
      <Route path="/dayn/:sessionId/lesson" element={<DayNLessonPage />} />
      <Route path="/compare" element={<ComparePage />} />
      <Route path="/eval" element={<EvaluationPage />} />
      <Route path="/about-design" element={<AboutDesignPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
