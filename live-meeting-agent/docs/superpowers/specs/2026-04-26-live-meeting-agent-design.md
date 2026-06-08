---
title: live-meeting-agent design
date: 2026-04-26
status: draft
author: Vico Strozzi
---

# live-meeting-agent

Active scribe that listens to a meeting through the laptop's audio, transcribes it locally, and writes/updates a `.drawio` file. The user opens the file in any drawio viewer (VS Code drawio extension, drawio desktop, app.diagrams.net) and shares that window in Teams. Every 5 minutes (or on a hotkey), the diagram is refreshed: existing entities keep their position, new ones are auto-placed.

## Goals
- Run alongside any meeting tool (Teams, Zoom, in-person with mic, recorded video) by capturing system audio, not by integrating with a specific platform.
- Produce a coherent, layout-stable `.drawio` file that can be screen-shared during the meeting and used as a reference afterwards.
- Auto-detect the diagram type (architecture / process flow / mindmap / sequence / entity model) so the user does not pre-configure each session.
- Preserve a per-cycle timeline of snapshots so the evolution of a workshop is reviewable later.

## Non-goals (v1)
- Speaker attribution or diarization.
- Multi-user collaboration on a shared canvas.
- Integration with Teams APIs (Graph, bot framework).
- Web embed for sub-second visual updates.
- Recorded-video processing (could be added trivially later).
- Glossary side-track, Teams chat narration, post-meeting summary report.

## Key decisions

| Decision | Choice | Rationale |
|---|---|---|
| Product intent | Active participant (B), with batch mode (C) as M1 | User can screen-share the diagram and let it shape the conversation. |
| Audio source | Local audio loopback + local Whisper | Lowest latency, works in any meeting tool, no external API or platform integration. |
| Diagram type | Auto-detect (LLM classifier) | User does not need to pre-configure; agent adapts to where the conversation goes. |
| Multi-page handling | One drawio page per detected type, plus per-cycle timeline pages | Native drawio feature, free history view. |
| State strategy | JSON logical model + deterministic XML generation | Layout stability across cycles. LLM cannot break positions. |
| Tech stack | Python | Best ecosystem for audio capture, Whisper, LLM SDKs. |
| Display surface | Plain `.drawio` file written to disk; user picks viewer | Decouples agent from viewer; minimum code; 5-minute cadence makes reload flash a non-issue. |

## Architecture

```
+------------+   +------------+   +----------+   +----------+   +-------------+
| Audio      |-->| Whisper    |-->| Rolling  |-->| Claude   |-->| JSON model  |
| loopback   |   | (local)    |   | buffer   |   | API      |   | (state.json)|
+------------+   +------------+   +----------+   +----------+   +-------------+
      ^                                ^                               |
   sounddevice                    5-min timer                          v
   (WASAPI)                       + hotkey                       +-------------+
                                                                 | XML gen +   |
                                                                 | auto-layout |
                                                                 +-------------+
                                                                       |
                                                                       v
                                                                meeting.drawio
                                                                (multi-page)
```

Six components, each independently testable:

### 1. Audio capture (`audio.py`)
- Uses `sounddevice` with WASAPI loopback to capture system output (what the user hears in Teams).
- Writes 16 kHz mono PCM into a thread-safe ring buffer of the last N minutes.
- Default ring buffer size: 30 minutes (configurable).
- Restarts itself if the audio device disappears (Bluetooth disconnect, sleep).

### 2. Transcription (`transcription.py`)
- Runs `faster-whisper` with the `medium.en` model in a background thread.
- Pulls 30-second chunks from the ring buffer, transcribes them, appends timestamped segments to the rolling transcript.
- Detects silence and skips empty chunks to save compute.

### 3. Rolling transcript (`model.py`)
- Append-only list of `{t, text}` segments.
- Persisted to `state.json` between cycles so a crash or restart loses at most the unprocessed audio in the ring buffer.

### 4. Trigger (`triggers.py`)
- 5-minute timer (configurable via `--interval`).
- Global hotkey `Ctrl+Shift+U` via the `keyboard` library for force-update.
- Both call the same handler.

### 5. LLM cycle (`llm.py`)
- One Claude call per cycle: input is the current JSON model plus new transcript segments since the last update; output is the updated JSON model with `active_diagram_type` and `pages`.
- Anthropic SDK with prompt caching applied to the system prompt + JSON schema. At a 5-minute cadence the cache hits roughly 90% of the time.
- Default model: `claude-sonnet-4-6`. Override via `--model claude-opus-4-7` for tougher sessions.

### 6. XML generator (`drawio.py`)
- Converts JSON model to mxGraph XML.
- Style per `kind`: system = rectangle, role = ellipse, store = cylinder, actor = person, etc.
- For new entities: dagre layout (via `networkx`) finds non-overlapping positions; positions are written back into the JSON so they are stable on the next cycle.
- For existing entities: positions read from JSON, never recomputed.
- Multi-page output:
  - One **live page per detected diagram type** (e.g., page 1 = architecture, page 2 = process flow if the conversation drifts there). The user shares whichever page is currently relevant in Teams.
  - **Timeline snapshot pages** appended at the end (e.g., `architecture - 14:05`, `architecture - 14:10`, ...). One snapshot per cycle.
  - **Archived page** for soft-deleted entities (see Failure modes). One per meeting.

## Data flow per cycle

1. Trigger fires (timer or hotkey).
2. Read transcript chunks since the last update from the rolling buffer.
3. Load `state.json` (current JSON model).
4. Single Claude call: classify diagram type and return the updated JSON model with stable IDs.
5. Validate JSON shape, drop unknown entity references, soft-delete missing entities (move to an `archived` page rather than removing them).
6. Compute the diff (added / changed / removed).
7. Generate mxGraph XML from the updated model and write `meeting.drawio` (live page + a new timeline snapshot page).
8. Save `state.json`.
9. Print the diff to the terminal, e.g. `+ MT Proxy (system) | ~ Translator -> MT Service | + edge: D365 -> MT Proxy`.

## State model

```json
{
  "meeting_id": "2026-04-26-festo-translator",
  "started_at": "2026-04-26T14:00:00",
  "active_diagram_type": "architecture",
  "pages": [
    {
      "type": "architecture",
      "entities": [
        {"id": "ent_001", "label": "D365", "kind": "system", "x": 120, "y": 80},
        {"id": "ent_002", "label": "MT Proxy", "kind": "system", "x": 360, "y": 80}
      ],
      "relations": [
        {"id": "rel_001", "from": "ent_001", "to": "ent_002", "label": "HTTPS"}
      ]
    }
  ],
  "transcript": [
    {"t": "14:02:15", "text": "..."}
  ]
}
```

**Ownership split:**
- LLM owns: `label`, `kind`, `type`, relation semantics.
- Code owns: `id` (stable, monotonic), `x`, `y` (auto-layout for new nodes; preserved for existing nodes).

This is the key invariant. Layout cannot break because the LLM does not control layout.

## Auto-detect strategy

The LLM is the classifier. The same per-cycle call is asked to return:

```json
{ "active_diagram_type": "architecture", "pages": [...] }
```

System prompt fragment: *"Stay with the current diagram type unless the conversation has clearly shifted to a different mode. Allowed types: architecture / process_flow / mindmap / sequence / entity_model."*

When the type changes, the agent creates a new page in the `.drawio` file and starts a fresh entity list for that page. Old pages are preserved.

## Tech defaults

| Decision | Choice | Notes |
|---|---|---|
| Whisper backend | `faster-whisper` `medium.en` | Offline, ~5x real-time on CPU, no audio leaves the machine. [ASSUMPTION: medium.en is good enough; large-v3 if quality drops.] |
| LLM | `claude-sonnet-4-6` (default), `claude-opus-4-7` flag | Best at structured JSON. Prompt caching cuts cost ~80% at 5-minute cadence. |
| Trigger | 5-minute timer + `Ctrl+Shift+U` hotkey | Configurable via `--interval`. Hotkey via the `keyboard` lib. |
| CLI entry | `python agent.py <meeting-name> [--interval 5m]` | Output written to `./meetings/<meeting-name>/`. |
| Layout engine | dagre via `networkx` | Battle-tested, no surprises. |

## Failure modes

| Failure | Mitigation |
|---|---|
| LLM returns invalid JSON | Retry once with a stricter prompt. On second failure, skip the cycle and log. |
| LLM hallucinates an entity ID that does not exist | Validation drops unknown references before XML generation. |
| LLM removes an entity that should stay | Soft delete: entity moves to an `archived` page, never gone. |
| Whisper produces a low-confidence chunk | Marked but kept. The LLM is robust to noisy text. |
| Audio loopback dies (Bluetooth disconnect, sleep) | Capture thread retries every 5s and prints status to the terminal. |
| Hotkey conflict with another tool | Configurable via `--hotkey`. Default `Ctrl+Shift+U` chosen to avoid common shortcuts. |

## Testing strategy

- **Unit tests** for `model.py` (JSON validation, diff), `drawio.py` (XML well-formed, layout deterministic for fixed seeds).
- **Golden-file tests** for the LLM cycle: fixed transcript fixtures, snapshot the resulting JSON model. Tests pass when the snapshot matches; an authorised script regenerates snapshots after a reviewed change.
- **Smoke test** for the audio pipeline: play a known WAV file through the system speakers, verify the transcript contains the expected words.
- **No mocks for the LLM in golden-file tests** unless cost becomes a problem; if it does, switch to recorded-and-replayed responses.

## Build sequence

| Milestone | Scope | Effort |
|---|---|---|
| **M1 - Batch pipeline** | Read a static transcript file, produce a one-page `.drawio` with auto-detected type. No audio, no live updates. Validates the LLM-JSON-XML chain end-to-end. This is the C-fallback. | 1-2 days |
| **M2 - Live audio** | Add `sounddevice` capture and `faster-whisper` transcription to a rolling buffer. Replace the static transcript file with the live buffer. Button-only updates. | 1-2 days |
| **M3 - Active participant** | Add the 5-minute timer, the global hotkey, and per-cycle multi-page snapshots. Result: option B. | 1 day |

Total: ~4-5 days of focused work to a usable v1.

## Repo layout

```
live-meeting-agent/
├── agent.py                # CLI entrypoint, orchestration
├── audio.py                # sounddevice loopback + ring buffer
├── transcription.py        # faster-whisper thread
├── llm.py                  # Claude API + prompt + caching
├── model.py                # JSON state schema, validation, diff
├── drawio.py               # JSON to mxGraph XML + dagre layout
├── triggers.py             # timer + hotkey
├── prompts/                # system prompts, JSON schema
│   ├── system.md
│   └── schema.json
├── meetings/               # output dir, gitignored
│   └── <meeting-name>/
│       ├── meeting.drawio
│       └── state.json
├── tests/
│   ├── fixtures/
│   ├── test_model.py
│   ├── test_drawio.py
│   └── test_llm_golden.py
├── requirements.txt
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-04-26-live-meeting-agent-design.md
├── README.md
└── .gitignore
```

## Future / out of scope

- **Speaker diarization** via `pyannote.audio` if speaker attribution becomes useful.
- **Glossary side-track** as a second auto-maintained page that captures every acronym, system name, or jargon term that comes up. Likely more valuable than the diagram in client workshops with heavy terminology.
- **Teams chat narration**: each cycle posts a short diff message ("Added MT Proxy as a new system, connected to D365 via HTTPS") so people who can not see the screen still follow along.
- **Web embed for smooth live updates** if the per-cycle reload flash ever becomes intrusive at sub-5-minute cadence.
- **Recorded-video processing**: feed an MP4 file through the same pipeline to produce a diagram from a past meeting.
- **Export to PowerPoint or markdown report** with the timeline snapshots embedded.

## Assumptions

- [ASSUMPTION] `medium.en` Whisper model is accurate enough for workshop dialogue with minor accents. Upgrade to `large-v3` if it is not.
- [ASSUMPTION] Bluetooth headsets do not exclusively lock the audio device when WASAPI loopback is active. Captures the system output, not the mic input, so the lock should not apply. To verify in M2.
- [ASSUMPTION] The `keyboard` Python library can register a global hotkey on Windows without admin privileges. To verify in M3.
- [ASSUMPTION] `claude-sonnet-4-6` produces stable JSON for the prompt at 5-minute cadence. To validate against golden-file tests in M1.
