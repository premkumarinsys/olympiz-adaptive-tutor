import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, BookOpen, Brain, ChatCircle, Target } from "@phosphor-icons/react";
import { api } from "./api";
import type { MockLearner } from "./types";
import "./open-chat.css";
type Action = "ask" | "prepare" | "practice" | "revise" | "answer";
type Exercise = { exercise_id: string; prompt: string; kind: string; hints: string[]; source?: string; source_label?: string };
type Message = { id: string; role: string; content: string; action: string; exercise?: Exercise; feedback?: { outcome: string; explanation: string; exercise_id?: string } };
type ChatSession = {
  session_id: string; learner_id: string; display_name: string;
  lesson: { lesson_id: string; title: string; teacher: string; objectives: string[]; outline: string[] };
  memory: { base_mode: string; modifiers: string[]; summary: string; evidence_count: number; state_version: number; provisional: boolean };
  messages: Message[]; suggestions: string[];
  trace: { nodes: string[]; provider: string; fallback_reason?: string };
};
const readable = (value = "") => value.replaceAll("_", " ");
const supportLabel = (value: string) => {
  const key = value.toLowerCase();
  if (key.startsWith("misconception_probe")) return "Check a confusing idea";
  if (key.startsWith("confidence_check")) return "Check confidence together";
  if (key.includes("small_chunk")) return "One step at a time";
  if (key.includes("visual")) return "Visual explanations";
  if (key === "balanced") return "Examples and explanations";
  if (key.includes("retrieval")) return "Recall before review";
  if (key.includes("foundation")) return "Build the foundations";
  if (key.includes("guided")) return "Guided practice";
  if (key.includes("challenge")) return "Independent challenge";
  return readable(value).replaceAll(":", ": ");
};
const base = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
async function chatRequest(path: string, body?: object): Promise<ChatSession> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 45000);
  try {
    const response = await fetch(base + "/api/v1/chat/sessions" + path, {
      method: body ? "POST" : "GET", headers: { "Content-Type": "application/json" },
      ...(body ? { body: JSON.stringify(body) } : {}), signal: controller.signal,
    });
    if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("The chat backend is unavailable. Please retry when it is connected.");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message || data.detail?.message || "The tutor could not complete that request. Please try again.");
    return data;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw new Error("The tutor took too long. Please retry your message.");
    throw error;
  } finally { window.clearTimeout(timeout); }
}
function TutorContent({ content }: { content: string }) {
  const inline = (text: string) => text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={index}>{part.slice(2, -2)}</strong> : part);
  const blocks: { kind: "paragraph" | "ordered" | "unordered" | "heading"; lines: string[]; level?: number }[] = [];
  let current: (typeof blocks)[number] | undefined;
  for (const line of content.split("\n")) {
    if (!line.trim()) { current = undefined; continue; }
    const heading = line.match(/^(#{1,6})\s+/);
    const kind = /^\s*\d+[.)]\s+/.test(line) ? "ordered" : /^\s*[-*•]\s+/.test(line) ? "unordered" : heading ? "heading" : "paragraph";
    const text = kind === "ordered" ? line.replace(/^\s*\d+[.)]\s+/, "") : kind === "unordered" ? line.replace(/^\s*[-*•]\s+/, "") : kind === "heading" ? line.replace(/^#{1,6}\s+/, "") : line;
    if (!current || current.kind !== kind || kind === "heading") {
      current = {kind, lines: [], level: heading ? Math.min(6, Math.max(2, heading[1].length)) : undefined}; blocks.push(current);
    }
    current.lines.push(text);
  }
  return <div className="chat-rich-content">{blocks.map((block, index) => {
    if (block.kind === "ordered" || block.kind === "unordered") {
      const items = block.lines.map((line, i) => <li key={i}>{inline(line)}</li>);
      return block.kind === "ordered" ? <ol key={index}>{items}</ol> : <ul key={index}>{items}</ul>;
    }
    if (block.kind === "heading") {
      const heading = inline(block.lines[0]);
      if (block.level === 3) return <h3 key={index}>{heading}</h3>;
      if (block.level === 4) return <h4 key={index}>{heading}</h4>;
      if (block.level === 5) return <h5 key={index}>{heading}</h5>;
      if (block.level === 6) return <h6 key={index}>{heading}</h6>;
      return <h2 key={index}>{heading}</h2>;
    }
    return <p key={index}>{block.lines.map((line, i) => <span key={i}>{i > 0 && <br/>}{inline(line)}</span>)}</p>;
  })}</div>;
}

export function OpenChatPage() {
  const [learners, setLearners] = useState<MockLearner[]>([]);
  const [selected, setSelected] = useState("");
  const [session, setSession] = useState<ChatSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyAction, setBusyAction] = useState<Action | "connect" | null>(null);
  const [error, setError] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [confidence, setConfidence] = useState("0.7");
  const [hintFor, setHintFor] = useState("");
  const [activeStage, setActiveStage] = useState<Action>("ask");
  const bottom = useRef<HTMLDivElement>(null);
  const pending = useRef(false);
  const retryTurn = useRef<{ signature: string; id: string } | null>(null);
  useEffect(() => { api.getMockLearners().then(items => {
    setLearners(items); setSelected(items.find(item => item.name.toLowerCase().includes("kabir"))?.learner_id ?? items[0]?.learner_id ?? "");
  }).catch(e => setError(e.message)); }, []);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [session?.messages.length]);
  const learner = learners.find(item => item.learner_id === selected);
  async function start(fresh = false) {
    if (!selected || pending.current) return;
    pending.current = true; setBusy(true); setBusyAction("connect"); setError(""); setSession(null);
    try {
      const saved = fresh ? null : sessionStorage.getItem("olympiz-chat-" + selected);
      let result: ChatSession;
      if (saved) {
        try { result = await chatRequest("/" + encodeURIComponent(saved)); }
        catch { result = await chatRequest("", { memory_fixture_id: selected }); }
      } else result = await chatRequest("", { memory_fixture_id: selected });
      setSession(result); sessionStorage.setItem("olympiz-chat-" + selected, result.session_id);
      setQuestion(""); setAnswer(""); setHintFor(""); setActiveStage("ask");
    } catch(e) { setError(e instanceof Error ? e.message : "Unable to connect to your tutor."); }
    finally { pending.current = false; setBusy(false); setBusyAction(null); }
  }
  useEffect(() => { if (selected) void start(); }, [selected]);
  async function send(action: Action, message: string, exerciseId?: string) {
    if (!session || pending.current || !message.trim()) return;
    pending.current = true; setBusy(true); setBusyAction(action); setError("");
    try {
      const signature = JSON.stringify([session.session_id, action, message.trim(), exerciseId, confidence, sessionStorage.getItem("olympiz-hint-" + exerciseId)]);
      if (retryTurn.current?.signature !== signature) retryTurn.current = { signature, id: crypto.randomUUID() };
      const next = await chatRequest("/" + encodeURIComponent(session.session_id) + "/messages", {
        client_turn_id: retryTurn.current.id, action, message: message.trim(),
        ...(exerciseId ? { exercise_id: exerciseId, confidence: Number(confidence), hints_used: sessionStorage.getItem("olympiz-hint-" + exerciseId) === "used" } : {}),
      });
      retryTurn.current = null; setSession(next); setActiveStage(action === "answer" ? "practice" : action);
      if (action === "ask") setQuestion("");
      if (action === "answer") setAnswer("");
      setHintFor("");
    } catch(e) { setError(e instanceof Error ? e.message : "Your message could not be sent."); }
    finally { pending.current = false; setBusy(false); setBusyAction(null); }
  }
  const latestExerciseMessage = [...(session?.messages ?? [])].reverse().find(message => message.exercise);
  const exercise = latestExerciseMessage?.exercise;
  const answered = exercise && session?.messages.slice(session.messages.indexOf(latestExerciseMessage!) + 1).some(message => message.feedback?.exercise_id === exercise.exercise_id && ["correct", "incorrect"].includes(message.feedback.outcome));
  useEffect(() => {
    setAnswer("");
    setConfidence("0.7");
    setHintFor("");
  }, [exercise?.exercise_id]);
  const stages: {action: Action; label: string; detail: string}[] = [
    {action: "ask", label: "Explore", detail: "Ask anything"},
    {action: "prepare", label: "Prepare", detail: "Build understanding"},
    {action: "practice", label: "Practice", detail: "Try it yourself"},
    {action: "revise", label: "Revise", detail: "Make it stick"},
  ];
  const busyMessage = busyAction === "answer" ? "Checking your answer..."
    : busyAction === "practice" ? "Creating your next practice problem..."
    : busyAction === "revise" ? "Building revision from your learning memory..."
    : busyAction === "prepare" ? "Preparing the next step..."
    : "Thinking through your question...";
  return <div className="chat-page">
    <header className="app-header chat-header">
      <Link className="brand" to="/" aria-label="Olympiz home">Olympiz</Link>
      <p className="welcome-copy">Your classroom lesson. <strong>Your way forward.</strong></p>
      <Link className="header-home-link" to="/dayn/select">Learning journeys <ArrowRight size={18}/></Link>
    </header>
    <div className="chat-layout">
      <aside className="chat-rail" aria-label="Student memory and class lesson">
        <section>
          <label className="section-kicker" htmlFor="chat-student">Learning with</label>
          <select id="chat-student" value={selected} disabled={busy} onChange={e => setSelected(e.target.value)}>
            {learners.map(item => <option value={item.learner_id} key={item.learner_id}>{item.name}</option>)}
          </select>
          <p className="chat-subtle">Saved learner profiles · prototype</p>
        </section>
        <section>
          <h2><Target size={20}/> Our class lesson</h2>
          <h3>{session?.lesson.title ?? "Newton’s laws of motion"}</h3>
          <p className="chat-static-tag"><BookOpen size={15}/> Shared teacher lesson</p>
          <p className="chat-subtle">The same lesson and objectives for every student.</p>
          {session && <details className="chat-lesson-details"><summary>View teacher’s lesson</summary>
            <p className="chat-subtle">{session.lesson.teacher}</p>
            <ul>{session.lesson.objectives.map(item => <li key={item}>{item}</li>)}</ul>
            <ol>{session.lesson.outline.map(item => <li key={item}>{item}</li>)}</ol>
          </details>}
        </section>
        <section>
          <h2><Brain size={20}/> What I remember</h2>
          <p className="chat-memory-copy">{session?.memory.summary ?? learner?.memory_preview.summary ?? "Loading your saved learning evidence…"}</p>
          <h3>Today’s support</h3>
          <strong className="chat-mode">{supportLabel(session?.memory.base_mode ?? learner?.base_mode ?? "")}</strong>
          <div className="chat-tags">{(session?.memory.modifiers ?? learner?.modifiers ?? []).map(item => <span key={item}>{supportLabel(item)}</span>)}</div>
          <p className="chat-subtle">A flexible starting point, updated by your exercise evidence.</p>
          {session?.memory.provisional && <p className="chat-subtle">Provisional · we’ll check what helps as you go.</p>}
        </section>
        <Link className="chat-back-link" to="/">All learning tools <ArrowRight size={16}/></Link>
      </aside>
      <main className="chat-main">
        <nav className="chat-stages" aria-label="Learning activities">
          {stages.map((stage, index) => <button key={stage.action} className={activeStage === stage.action ? "active" : ""} disabled={busy || !session} aria-current={activeStage === stage.action ? "step" : undefined}
            onClick={() => stage.action === "ask" ? (setActiveStage("ask"), document.getElementById("chat-question")?.focus()) : void send(stage.action, stage.action === "prepare" ? "Help me prepare for the class exercises." : stage.action === "practice" ? "Give me a personalized practice problem." : "Help me revise based on my learning memory.")}>
            <span className="chat-stage-number">{index + 1}</span><span><strong>{stage.label}</strong><small>{stage.detail}</small></span>
          </button>)}
        </nav>
        <div className="chat-conversation">
          <div className="chat-title-row"><div><p className="section-kicker">Open tutor · {session?.display_name ?? learner?.name ?? "Your learning space"}</p><h1>Let’s work through it together.</h1></div>
            {session && <button className="text-button" disabled={busy} onClick={() => void start(true)}>New chat</button>}
          </div>
          <p className="chat-intro">Bring a question from class, get ready for an exercise, or revisit something that hasn’t clicked yet.</p>
          {!session && <div className="chat-connecting" role="status">{busy ? "Connecting your lesson and learning memory…" : "Your tutor will appear here once connected."}</div>}
          {session?.trace.fallback_reason && ["PROVIDER_NOT_CONFIGURED", "PROVIDER_UNAVAILABLE"].includes(session.trace.fallback_reason) && <p className="chat-source-notice" role="status">Limited lesson guide · open-ended AI responses are currently unavailable. You can still ask about the lesson basics and work through verified exercises.</p>}<div className="chat-messages" role="log" aria-label="Tutor conversation" aria-live="polite">
            {session?.messages.map((message, index) => <article className={"chat-message " + (message.role === "user" ? "from-student" : "from-tutor")} key={message.id ?? index}>
              <div className="chat-message-label">{message.role === "user" ? <span>{session.display_name.slice(0,1)}</span> : <ChatCircle size={21}/>}<strong>{message.role === "user" ? "You" : "Olympiz tutor"}</strong></div>
              <TutorContent content={message.content}/>
              {message.exercise && <section className="chat-exercise" aria-labelledby={"exercise-title-" + message.exercise.exercise_id}><p className="section-kicker">Your turn · personalized practice</p>{message.exercise.source_label && <p className="chat-exercise-source">{message.exercise.source_label}</p>}<h2 id={"exercise-title-" + message.exercise.exercise_id}>{message.exercise.prompt}</h2>
                {message.exercise.exercise_id === exercise?.exercise_id && !answered ? <>
                  {message.exercise.hints?.length > 0 && <><button className="text-button" disabled={busy} onClick={() => { sessionStorage.setItem("olympiz-hint-" + message.exercise!.exercise_id, "used"); setHintFor(hintFor ? "" : message.exercise!.exercise_id); }} aria-expanded={hintFor === message.exercise.exercise_id}>{hintFor ? "Hide hint" : "I’d like a hint"}</button>
                    {hintFor === message.exercise.exercise_id && <p className="chat-hint">{message.exercise.hints[0]}</p>}</>}
                  <form onSubmit={e => {e.preventDefault(); void send("answer", answer, message.exercise!.exercise_id);}}>
                    <label htmlFor={"answer-" + index}>Your answer</label><input id={"answer-" + index} value={answer} onChange={e => setAnswer(e.target.value)} placeholder={message.exercise.kind === "numeric" ? "One number, optionally with units" : "Your answer"} disabled={busy} required maxLength={4000}/>
                    <div className="chat-answer-actions"><label>How sure are you?<select value={confidence} onChange={e => setConfidence(e.target.value)} disabled={busy}><option value="0.2">Still figuring it out</option><option value="0.45">Somewhat sure</option><option value="0.7">Confident</option><option value="0.95">Very confident</option></select></label>
                      <button className="primary-button" disabled={busy || !answer.trim()}>Check answer <ArrowRight size={17}/></button></div>
                  </form></> : <p className="chat-subtle">This exercise is in your conversation history.</p>}
              </section>}
              {message.feedback && <div className={"chat-feedback " + (message.feedback.outcome === "incorrect" ? "needs-review" : "")}>{message.feedback.outcome === "correct" ? "Answer checked · correct" : message.feedback.outcome === "incorrect" ? "Answer checked · revisit this concept" : (message.feedback.exercise_id === exercise?.exercise_id && !answered ? "Answer not graded · try again above" : "This earlier answer was not graded")}</div>}
            </article>)}
          </div>
          {busy && session && <p className="chat-thinking" role="status">{busyMessage}</p>}
          {error && <div className="inline-error" role="alert">{error}{!session && <button onClick={() => void start()} disabled={busy}>Retry connection</button>}</div>}
          <div ref={bottom}/>
        </div>
        <div className="chat-composer-wrap">
          {session && <div className="chat-suggestions" aria-label="Suggested questions">{session.suggestions.slice(0,3).map(item => <button key={item} disabled={busy} onClick={() => void send(/prepar/i.test(item) ? "prepare" : /revis/i.test(item) ? "revise" : /practice/i.test(item) ? "practice" : "ask", item)}>{item}<ArrowRight size={14}/></button>)}</div>}
          <form className="chat-composer" onSubmit={e => {e.preventDefault(); void send("ask", question);}}>
            <label className="sr-only" htmlFor="chat-question">Ask your tutor a question</label>
            <textarea id="chat-question" rows={2} value={question} onChange={e => setQuestion(e.target.value)} maxLength={4000} disabled={busy || !session} placeholder="What would you like to understand?"/>
            <button className="primary-button" disabled={busy || !session || !question.trim()} aria-label="Send question"><ArrowRight size={22}/></button>
          </form>
          <p className="chat-composer-note">Questions guide the conversation. Checked exercises help update your learning memory.</p>
        </div>
      </main>
    </div>
    <footer className="chat-session-band"><span><strong>Same class lesson</strong><small>Personal support, at your pace</small></span><span><strong>{session?.messages.filter(m => m.role === "user").length ?? 0} contributions</strong><small>{session ? "Memory version " + session.memory.state_version : "Connecting memory"}</small></span>
      {session && <details className="chat-trace"><summary>Decision trace</summary><div><strong>How this response was prepared</strong><p>Response source: {readable(session.trace.provider)}</p>{session.trace.fallback_reason && <p>{session.trace.fallback_reason}</p>}<ol>{session.trace.nodes.map(node => <li key={node}>{readable(node)}</li>)}</ol><p>{session.memory.evidence_count} saved evidence events · {session.memory.provisional ? "Provisional" : "Current"} support strategy</p></div></details>}
    </footer>
  </div>;
}
