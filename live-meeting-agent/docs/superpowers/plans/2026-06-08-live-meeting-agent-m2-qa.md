# Live Meeting Agent - M2 (Reactive Q&A) Implementation Plan

> Sub-skill: subagent-driven-development / executing-plans. Commit on Vico's go-ahead.
> Daily-driver-safe: pure additions to the brain + server + UI; no tray change.

**Goal:** Ask the live transcript questions in the same window - "summarize so far", "decisions", "action items", "who said X", "draw a drawio" - answered by Claude, streamed back token-by-token.

**Architecture:** `brain/qa.py` builds a system prompt carrying the speaker-attributed transcript (prompt-cached) + the question, and streams Claude's reply via the anthropic SDK. FastAPI gets `POST /api/ask` (chunked streaming). The React app gets a chat panel (input + preset buttons) that streams the answer. Mixed DE/EN: Claude replies in the question's language.

**Prereq:** `ANTHROPIC_API_KEY` env var (the app's own key for the anthropic SDK). Build + unit tests don't need it; live answers do.

**Tech:** anthropic SDK, FastAPI StreamingResponse, React fetch-stream. Builds on M1A/M1B.

---

## Task 1: anthropic dependency
- [ ] Append to `requirements.txt`: `# Q&A (M2)` + `anthropic>=0.40`; install; verify import.
- [ ] Commit `chore(qa): add anthropic SDK`.

## Task 2: qa.py (prompt + streaming)
**Files:** `lma/brain/qa.py`, `tests/test_qa.py`
- [ ] Test (no API key): `build_messages(transcript, q)` returns 2 system blocks (prompt + transcript with `cache_control`) and user text == resolved question; `resolve_question("summary")` -> the preset text, `resolve_question("free")` -> "free".
- [ ] Implement `SYSTEM_PROMPT`, `PRESETS`, `resolve_question`, `build_messages`, `ask_stream(transcript, question, *, model, client) -> Iterator[str]` (anthropic `messages.stream`, lazy import).
- [ ] Gated live test (`RUN_CLAUDE=1`): ask "summary" over a tiny transcript -> non-empty text.
- [ ] Commit.

## Task 3: server /api/ask (streaming)
**Files:** `lma/server/server.py`, `tests/test_server.py`
- [ ] `create_app(..., ask_fn=None)`: `ask_fn(question)->Iterator[str]`; default binds `qa.ask_stream(transcript, ...)`. `POST /api/ask {question}` -> `StreamingResponse(ask_fn(resolve_question(question)), media_type="text/plain")`.
- [ ] Test: inject `ask_fn=lambda q: iter(["hel","lo"])`; POST -> body "hello".
- [ ] Commit.

## Task 4: chat panel (React)
**Files:** `lma/server/frontend/src/Chat.tsx` (+ hook), `App.tsx`, `App.css`; rebuild
- [ ] `useAsk()` hook: POST /api/ask, read the streamed body (ReadableStream reader), accumulate into the answer state.
- [ ] `Chat` component: preset buttons (Summary / Decisions / Actions / Questions / Draw drawio) + free-text input + streamed answer area (monospace, preserves fenced code).
- [ ] App layout: transcript pane (scroll) + chat panel below; rebuild `dist`.
- [ ] Commit (incl. rebuilt dist).

## Task 5: drawio artifact (thin)
- [ ] In `qa.py` add `extract_drawio(answer) -> Optional[str]` (pull a ```xml ... ``` block). Endpoint `POST /api/save-drawio {xml,name}` writes `<recordings>/artifacts/<name>.drawio`, returns path. UI "save .drawio" button when the answer contains drawio XML. (Optional; can defer.)
- [ ] Commit.

## Task 6: E2E (user)
- [ ] `setx ANTHROPIC_API_KEY ...` (once). `python -m lma.serve --source <flac>`, click "Summary" -> streamed answer; type "wer hat was zu Blocks gesagt?" -> German answer.

## Self-review
- Q&A over transcript (spec reactive commands): T2. Streaming endpoint: T3. Chat UI + presets + draw: T4/T5. DE/EN: prompt instructs reply-in-question-language. Daily-driver untouched.

## Deferred
- M4 auto-launch (tray spawns brain+server+window on meeting start). M3 diarization (Speaker 1/2/3).
