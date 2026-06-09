# Meeting Archive (M6) - Design

**Goal:** A persistent "admin" app to browse, search, and chat against **past** meeting transcripts - so you don't dig through `recordings/` folders. Each meeting shows an auto-generated **title**, date/time, and duration; you can open the full speaker-attributed transcript and ask Claude questions about any meeting.

**Relationship to the live agent:** the live agent (M1-M5) handles the *current* call. The Archive is the *after-the-fact* companion over everything already recorded. It reuses the same transcript format, Q&A engine, and React/FastAPI stack.

---

## What already exists (reused)
- Transcripts are saved per meeting as `recordings/YYYY-MM/<id>.transcript.jsonl` (one Segment per line: start, end, text, speaker, channel). ✓
- Q&A engine: `lma/brain/qa.py` (`build_client` → Foundry Claude, `ask_stream`, presets, drawio). ✓
- FastAPI server + Vite/React UI + pywebview window shell. ✓

## What's new
1. **Metadata + index** - derive a per-meeting record; build a sortable/searchable list.
2. **Auto-titling** - Claude turns each transcript into a title + summary + topics.
3. **Archive server + UI** - list / detail / search / chat.
4. **Launcher** - "Open Meeting Archive" tray item; runs independently of any call.

---

## Data model - `recordings/YYYY-MM/<id>.meta.json` (sidecar)
```json
{
  "id": "260608_073714",
  "title": "Festo routing - decision on Variante C",
  "summary": "Agreed to use Variante C for routing; open follow-up on queue config.",
  "topics": ["Festo", "routing", "Variante C"],
  "started_at": "2026-06-08T07:37:14",
  "duration_s": 63.6,
  "speakers": ["You", "Speaker 1", "Speaker 2"],
  "segments": 42,
  "title_model": "claude-sonnet-4-6",
  "generated_at": "2026-06-08T15:10:00"
}
```
`id` + `started_at` come from the filename; `duration`/`speakers`/`segments` from the jsonl; `title`/`summary`/`topics` from Claude. The sidecar is the cache so titling runs once per meeting.

## Components
- **`lma/archive/index.py`** - scan `recordings/**/*.transcript.jsonl`, pair with `.meta.json`, derive missing fields, return a list sorted newest-first. Pure file-based, no DB.
- **`lma/archive/titler.py`** - `generate_meta(transcript_text) -> {title, summary, topics}` via Foundry Claude (reuses `qa.build_client`). Lazy: when the archive encounters a transcript without a `.meta.json`, it generates and caches one. Plus a one-off **backfill** entry (`python -m lma.archive.backfill`) to title all existing recordings at once.
- **`lma/archive/server.py`** - FastAPI on a **separate port (8732)** so it can be open alongside the live agent:
  - `GET /api/meetings` → list (id, title, summary, started_at, duration, speakers, topics)
  - `GET /api/meetings/{id}` → full transcript segments
  - `POST /api/meetings/{id}/ask` → stream a Claude answer grounded in that meeting (reuses `qa.ask_stream`)
  - `GET /api/search?q=...` → meetings whose title/summary/transcript match
  - serves the archive UI
- **Archive UI** - extend the existing Vite/React app with an **Archive view**: left = searchable meeting list (title, date, duration); right = transcript + a chat panel (the existing Chat component, pointed at `/api/meetings/{id}/ask`).
- **Launcher** - tray menu **"Open Meeting Archive"** spawns `python -m lma.archive` (pywebview window on 8732). Also runnable standalone. Independent of any live call, so you can leave it open all day.

## Scope
**v1 (this build):**
- Browse all meetings with auto-titles, date, duration, speakers.
- Open + read any transcript (timestamps + speaker labels).
- Keyword search across titles/summaries/transcript text.
- Chat (Q&A) against **one selected meeting**.
- Lazy auto-titling + a backfill command.

**v2 (later, not now):**
- Chat **across all meetings** ("what did we decide about Festo last month?") - needs retrieval/embeddings.
- Semantic search.
- Editing/renaming, export, tagging UI.

**Non-goals:** multi-user/auth, cloud hosting, editing transcripts.

## Build sequence (tasks)
1. `index.py` + tests (derive metadata from jsonl; pair sidecars).
2. `titler.py` (Claude title/summary/topics) + lazy cache + `backfill` command + tests.
3. `archive/server.py` endpoints (list/detail/ask/search) on 8732 + tests.
4. Archive React view (list / detail / search / chat) - extend the existing app.
5. Launcher: tray "Open Meeting Archive" + `lma/archive/__main__.py` (pywebview window).
6. End-to-end check against your existing recordings; docs + CLAUDE.md update.

## Open decisions (your call at approval)
1. **Title language:** title/summary in the meeting's language, or always English? (default: **meeting's language**)
2. **Auto-title timing:** lazy-on-first-view + backfill (default) - or also generate immediately when each meeting ends? (default: **lazy + backfill**, keeps the recording path decoupled)
3. **Always-open:** just a tray launcher (default) - or also auto-open the Archive at logon? (default: **launcher only**)
