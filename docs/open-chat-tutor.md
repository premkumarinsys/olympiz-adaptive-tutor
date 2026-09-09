# Open chat tutor

The teacher lesson is the shared curriculum for the whole class. Personalization happens in the conversation, preparation exercises, and revision that surround it. The tutor must not silently replace that lesson with the existing adaptive Day N lesson plan.

## Student memory and support

The existing learner event stream is the source of learning evidence. Its reducer produces per-concept mastery and uncertainty, scaffolding need, misconceptions, calibration, representation preferences, and pace signals. Each support decision should retain its evidence references.

Foundation, guided, and challenge describe the support appropriate now, not a permanent category of student. The existing policy requires sufficient, fresh, independently demonstrated evidence before choosing challenge; a prerequisite gap selects foundation. Sparse evidence falls back to guided support. Representation and pace are additional support choices, not learning-style diagnoses.

A student asking a question has expressed an interest or a need for help. That question is not a graded response and must not increase mastery, confirm a misconception, or count as successful revision. Conversation history is separate from assessed learning evidence.

## Shared lesson, different follow-up

All learners receive the same teacher-authored lesson identity, objectives, sequence, and core explanation. A student who needs prerequisite support may receive a net-force warm-up; a student with stronger evidence may receive a transfer problem. Both remain anchored to the same class lesson.

Practice and revision can use constrained model-generated parameters or verified catalog problems. Trusted backend code writes and solves generated questions, keeps answer keys server-side, and rejects unsupported or malformed output. Explanations can be adapted to current support needs. The tutor should explain why a practice set was selected using understandable observations rather than labels about ability or motivation.

## Conversation boundaries

Conversation state belongs to one learner. Switching learners must not reuse another learner's messages or pending exercises. A backend conversation identifier must be checked against its owning learner.

Free-form question answering requires a separate conversational model prompt; the existing lesson renderer only controls connective style and cannot provide arbitrary answers. If a provider is absent or fails, the interface must identify the response as a lesson-guide fallback. A deterministic fallback can offer supported explanations and next steps, but should not pretend to answer every question.

The teacher material and verified content anchor a model response. Student messages remain questions or answers, never instructions to rewrite the teacher lesson, change policy thresholds, or write mastery evidence.

## Validation targets

- The teacher lesson is identical across the fixture learners.
- The same lesson produces different follow-up support when learner evidence differs.
- Asking a question leaves assessed learner state unchanged.
- Learner conversations remain isolated.
- Practice payloads do not expose answer keys.
- Provider failures and unavailable configuration produce an explicit fallback.
- Any recorded practice evidence comes from a graded response, with repeat submission protection.


## Implemented API and prototype scope

- POST /api/v1/chat/sessions accepts exactly one of memory_fixture_id or learner_id.
- GET /api/v1/chat/sessions/{session_id} restores the conversation and refreshes reduced memory.
- POST /api/v1/chat/sessions/{session_id}/messages accepts client_turn_id, action (ask, prepare, practice, revise, answer), message, and optional exercise_id, confidence and hints_used.
- Answers return feedback.exercise_id and outcome (correct, incorrect, ungradable). Ungradable input remains retryable. Reusing a turn ID with different input returns a conflict.

ChatTutor compiles a separate bounded LangGraph: read_student_memory -> personalize_within_class_lesson. It reuses the existing event repository, state reducer, evidence-based policy, verified catalog, grader and configured model client. The current shared lesson is the pinned Newton's second law sample in CLASS_LESSON; teacher lesson import/editing is outside this prototype.

Practice presents a personalized set progressively, one problem per Practice or Revise action. A separate three-node generation graph selects an approved exercise template from current memory, asks the configured model only for a scenario and bounded whole-number parameters, then validates, authors, solves, and deduplicates the final problem in trusted code. Revision prioritizes stale and weaker concept evidence after misconception repair. Missing, malformed, or duplicate model output falls back to the verified catalog. Model-generated answer keys are never accepted or exposed.

Open questions use the configured Responses or compatible Chat Completions client with the shared lesson, current support signals and 12 recent messages. Conversational prose is model-generated and is not formally claim-validated like the original deterministic lesson renderer. Model calls have no grading or memory-write capabilities. Provider failure or missing configuration falls back to explicitly limited lesson guidance. This flow does not reuse the lesson renderer's connective-style schema.

Conversations persist in data/runtime/chat_sessions; the browser remembers the selected learner's conversation in sessionStorage. Graded exercise events join that learner's existing event stream. Hints affect support evidence only when reported opened. This remains a local prototype with selectable synthetic learners, no authentication or production authorization boundary, and single-process file locking. Session IDs isolate exercises and history but are not credentials.

## Verification

The backend unit suite passes, including chat coverage for fixed lesson identity, different difficulty and scaffolding, unchanged memory on questions, history isolation and persistence, hidden answer keys, retry conflicts, ungradable retry, provider context, explicit concept-targeted revision, bounded parameter validation, unit-aware server-side grading, generated-answer grading, and verified-catalog fallback. Live browser checks cover model-generated practice, source labeling, and graded feedback. The existing golden policy evaluation passes; it is not evidence of real learning gains.
