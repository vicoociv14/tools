---
title: Live Meeting Agent (unified) - design
date: 2026-06-07
status: draft
author: Vico Strozzi
supersedes-intent-of: 2026-04-26-live-meeting-agent-design.md (drawio diagram generator, now shelved)
absorbs: whisp-rec recorder (C:\Tools\whisp-rec), whisp transcription skill (claude-hub)
---

# Live Meeting Agent (unified)

One package that records every Teams meeting, transcribes and **diarizes it live**, and acts as a **reactive sparring partner**: a chat window where you ask things about the meeting-in-progress ("summarize so far", "what did we decide", "who pushed back on the cache idea", "draw a drawio of the architecture") and it answers from a live, speaker-attributed transcript. Your own voice is "You"; remote participants are split into Speaker 1 / 2 / 3.

It is built by **merging the existing, working `whisp-rec` recorder** (capture + Teams auto-detect + hotkey + tray + archive) with a **new "live brain"** (streaming transcription + rolling diarization + Claude Q&A + chat UI). The FLAC archive and post-meeting transcription keep working exactly as today; the live brain is additive.

## The one core idea

Keep a live, speaker-attributed transcript in memory. On every chat message, hand that transcript to Claude with your question. Everything else is plumbing - and most of the capture plumbing already exists.

---

## Current assets (verified on disk, 2026-06-07)

These are reused, not rebuilt. Facts below come from reading `C:\Tools\whisp-rec` and the claude-hub `whisp` plugin.

| Asset | Location | What it does | Fate in the merge |
|---|---|---|---|
| `recorder.py` | `C:\Tools\whisp-rec` | `soundcard` WASAPI capture: **mic = Left, system = Right**, stereo FLAC 48 kHz PCM_16, threaded readers + 500 ms buffers (Bluetooth-safe) -> `C:\recordings\YYYY-MM\YYMMDD_HHMMSS.flac` | Lift into package; add a **fan-out tap** to a live audio bus |
| `teams_detect.py` | `C:\Tools\whisp-rec` | pycaw audio-session poll for `ms-teams.exe`/`Teams.exe`; start after 2 polls (~10 s), stop after 6 (~30 s); dedicated COM-MTA thread | Lift as-is (drives meeting + brain lifecycle) |
| `tray.py` | `C:\Tools\whisp-rec` | State machine (IDLE / RECORDING_MANUAL / RECORDING_AUTO), Win32 `RegisterHotKey` (`Ctrl+Alt+R`), tray icon + menu | Lift; extend menu (open chat, speakers) |
| `overlay.py` | `C:\Tools\whisp-rec` | Tkinter REC timer pill, top-right, hide-able for screen-share | Lift as-is |
| `config.json` | `C:\Tools\whisp-rec` | All knobs incl. `auto_transcribe` (OFF), `transcribe_python`, model, Teams thresholds | Become the package config (superset) |
| `install.ps1` | `C:\Tools\whisp-rec` | venv + Task Scheduler `whisp-rec` task ("At log on", silent `pythonw tray.py`) | Adapt to launch the merged entry point; repoint the task |
| transcription engine | `C:\Tools\whisper` (venv) | faster-whisper 1.2.1 / ctranslate2, `large-v3-turbo`, int8, CPU | Shared HuggingFace model cache; engine reused |
| `whisp` skill | `C:\Repos\claude-hub\plugins\whisp` | Claude Code skill for **ad-hoc** file transcription (`transcribe.py`, `latest` shortcut) | **Stays independent** - useful on its own; shares `C:\recordings` + model cache |

**Key alignment:** `whisp-rec` already records the exact channel layout the design needs - **mic (L) = "You", system (R) = the people to diarize**. We do not build capture; we add the live layer on top of it.

**The gap being closed:** `whisp-rec` is batch (record whole FLAC, then transcribe the file). The sparring partner needs the same audio **live and incremental**, plus the chat UI.

---

## Decisions (locked in brainstorming)

| Decision | Choice |
|---|---|
| Interaction model | Standalone chat app |
| App shell | Local web UI, wrapped in `pywebview` for a desktop window + tray (web tech inside, desktop feel outside) |
| Speaker attribution | Acoustic diarization (pyannote) into Speaker 1/2/3 |
| Your voice | Mic channel pinned to "You" (free, accurate); pyannote only on the system channel |
| Diarization timing | Rolling in background, persistent embedding registry for stable labels |
| Diarizer build | Roll our own (pyannote per chunk + registry) |
| Merge structure | **Merge into one package** in the `live-meeting-agent` repo; one process captures once and fans audio to FLAC archive + live brain; repoint the logon task |
| Live brain lifecycle | **Auto-live every meeting** (brain starts when a recording starts), with graceful degradation and a config switch to dial back |
| Existing diagram code | Shelved, untouched (`agent.py`, `llm.py`, `drawio.py`, `model.py`, old `audio.py`/`transcription.py`) |
| Live transcription | Chunked faster-whisper on a rolling buffer (separate from the batch/post-meeting full-file pass) |
| Q&A model | `claude-sonnet-4-6` default, opus override; prompt caching on the transcript prefix |

---

## Architecture

One Python process. The **capture core** is light and always-on (it is your recorder). The **live brain** auto-attaches when a recording starts.

```
                         ┌─────────────────────── capture core (always on) ───────────────────────┐
[mic]   ─┐               │  recorder.py (soundcard, 48 kHz stereo)                                 │
         ├─ soundcard ─► │   ├─► FLAC writer ─► C:\recordings\YYYY-MM\YYMMDD_HHMMSS.flac (archive) │
[system]─┘  (WASAPI)     │   └─► fan-out tap ─► live audio bus (per-channel 16 kHz ring buffers)   │
                         │  teams_detect.py (pycaw) ─► meeting start/stop                          │
                         │  tray.py (Win32 hotkey Ctrl+Alt+R, tray menu) + overlay.py (REC pill)   │
                         └──────────────────────────────┬──────────────────────────────────────────┘
                                 meeting starts ───────►│ (auto-live)
                         ┌──────────────────────────────▼──────── live brain (per meeting) ────────┐
                         │  transcriber: system = continuous chunked whisper                        │
                         │              mic    = VAD-gated chunked whisper ("You")                   │
                         │  diarizer:   pyannote on system channel, every ~90 s,                     │
                         │              sliding window + persistent speaker registry                 │
                         │  merger:     mic seg -> "You"; system seg -> overlapping pyannote speaker │
                         │              -> unified transcript -> persist .jsonl + broadcast (WS)     │
                         │  qa:         question + transcript (cached) -> Claude (streamed)          │
                         │  server:     FastAPI (WS transcript, WS chat, control, speakers)          │
                         │  shell:      pywebview window + tray entry ("Open chat")                  │
                         └──────────────────────────────┬──────────────────────────────────────────┘
                                 meeting ends ─────────►│ tear down brain; optional clean re-diarization
                                                        ▼
                          per-meeting sidecars next to the FLAC:
                          YYMMDD_HHMMSS.transcript.jsonl, .speakers.json, .summary.md, artifacts\
```

### Components

**Capture core (lifted from whisp-rec, minimal change):**

1. `capture/recorder.py` - existing soundcard capture. **One change:** after reading each audio chunk it already routes to the FLAC writer; add a **fan-out tap** that also pushes the chunk (per channel) onto the live audio bus. The tap is near-free and is skipped when no brain consumer is attached.
2. `capture/bus.py` *(new)* - per-channel ring buffers at 16 kHz mono (downsampled from 48 kHz), absolute-time indexed. Channel L -> "you" buffer, channel R -> "system" buffer. This is the seam between capture and brain.
3. `capture/teams_detect.py`, `capture/tray.py`, `capture/overlay.py` - lifted as-is; `tray.py` gains menu items ("Open chat", "Speakers") and `hotkey` stays `Ctrl+Alt+R`.

**Live brain (new):**

4. `brain/transcriber.py` - chunked faster-whisper. **System** worker pulls ~15-20 s windows continuously (beam=1, VAD on). **Mic** worker is VAD-gated (only transcribes when you actually speak - cheap). Each emits timestamped segments tagged by channel. Live model is configurable and defaults smaller than the archive model for latency (see Tech defaults).
5. `brain/diarizer.py` - rolling pyannote on the **system** channel only. Every ~90 s it takes a trailing, overlapping window, gets speaker turns, embeds each within-window cluster, and matches them to a **persistent speaker registry** by cosine similarity (match -> update centroid; no match -> new Speaker). Cadence/window/threshold are tunable to fit the CPU.
6. `brain/merger.py` - mic segments -> "You". System segments -> stamped with the pyannote speaker whose turn overlaps them most. Builds the unified transcript, appends to the `.transcript.jsonl` sidecar, broadcasts updates.
7. `brain/state.py` - thread-safe `MeetingState`: bus handles, unified transcript, speaker registry. Persistence: `.transcript.jsonl` (append-per-segment) and `.speakers.json`.
8. `brain/qa.py` - on each chat message builds system prompt + current speaker-attributed transcript (prompt-cached prefix) + question -> streams Claude. Presets are canned questions. A "draw" request returns drawio XML in a fenced block, extracted and written as a `.drawio` artifact.
9. `brain/lifecycle.py` - starts/stops the brain when a recording starts/stops, per the `live_brain` config (auto / on-demand / off). Owns graceful degradation.

**Server + UI (new):**

10. `server/server.py` - FastAPI: serves the SPA, `WS /ws/transcript`, `WS /ws/chat`, control + speaker endpoints. Bridges background threads to async WS via `run_coroutine_threadsafe`.
11. `server/shell.py` - `pywebview` window (desktop feel) opened from the tray; the FastAPI server runs locally and the webview points at it.
12. `server/frontend/` - **Vite + React** SPA (built to static assets, served by FastAPI): live colour-coded transcript, speaker legend (rename/merge), chat thread + quick actions, status bar with a **diarization-lag indicator**.

**Post-meeting (new, thin):**

13. `transcription_batch.py` - when a meeting ends, optionally run a **full-file clean pass**: high-quality whisper (`large-v3-turbo`) + a one-shot full-recording diarization (pyannote clusters the whole file at once -> most accurate labels) -> a clean `.transcript.md`. This is the quality counterpart to the live (lower-latency) transcript, and reuses the same engine as the `whisp` skill.

---

## Audio model

`whisp-rec` records **mic = Left, system = Right**, 48 kHz stereo FLAC.

- **mic (L) -> "You".** VAD finds where you speak; those windows are transcribed and labelled "You". No diarization (it is your channel).
- **system (R) -> Speaker 1/2/3.** Transcribed continuously and diarized by pyannote.

The brain consumes 16 kHz mono per channel from the bus (downsampled from 48 kHz). Overlap (you and a remote talking at once) simply yields two segments.

[ASSUMPTION] You wear headphones (already the operating assumption of `whisp-rec`); otherwise the mic re-captures remote audio and attribution doubles.

---

## Rolling diarization with a persistent registry

The registry keeps "Speaker 2" the same person all meeting.

**Registry entry:** `{ id: "spk_1", label: "Speaker 1" (editable), centroid: float[], count: int, last_seen: float }`.

**Per cadence (default 90 s):**
1. Take a trailing window of the system channel (default last ~180 s, overlapping the previous window).
2. Run the pyannote diarization pipeline -> within-window clusters + turns.
3. Embed each within-window cluster (mean of its turn embeddings).
4. Match each cluster to the registry by max cosine similarity: `>= threshold` (default 0.70) -> assign + update centroid; else -> new Speaker.
5. Write absolute-time turns into the speaker timeline; for the overlapped region keep the prior assignment (overlap is for label continuity, not relabelling).

**Honest limits:** diarization on codec-compressed, overlapping Teams audio is imperfect; similar voices merge, one person can split. Mitigations: UI **rename + merge**, and the **post-meeting full re-diarization** for a clean final record.

---

## Reactive commands

Free-form chat plus quick-action buttons (all the same operation underneath - question + transcript -> streamed reply):

- Summarize the meeting so far
- Key decisions so far
- Action items (owner = the speaker who took it)
- Open questions / points of disagreement
- "Who said / who pushed back on X"
- Draw a drawio of <topic> (writes a `.drawio` artifact)

No fixed feature menu - you can ask anything.

---

## Web / desktop UI

FastAPI serves a single-page app; `pywebview` wraps it in a native window opened from the tray (no browser tab to manage). Panes: live colour-coded transcript (auto-scroll, timestamped, labelled), speaker legend with inline rename/merge, chat thread with quick actions and artifact links, and a status bar (recording state, model, **diarization-lag**).

**Window behaviour:** the brain runs automatically with the meeting; the **window opens on demand** from the tray (or hotkey), so it never pops up uninvited mid-call. Optional `auto_open_window` config (default off).

**Stack:** **Vite + React** SPA (matches your telemetry-visualizer pattern), built to static assets and served by FastAPI; `pywebview` points at the local server. Dev uses the Vite dev server proxying the API/WS; production serves the built bundle.

### API surface
- `GET /` - SPA.
- `WS /ws/transcript` - pushes `{type:"segment"}`, `{type:"speakers"}`, `{type:"status", recording, diarize_lag}`.
- `WS /ws/chat` (or `POST /chat` + SSE) - `{question}` -> stream `{token}` ... `{done, artifacts}`.
- `POST /control/start|stop` - manual recording control (mirrors hotkey).
- `POST /speakers/rename {id,label}`, `POST /speakers/merge {from,into}`.
- `GET /export?fmt=md|jsonl`.

---

## Process, threading, lifecycle

Single process (`pythonw` via the logon task, as today). Threads:

- capture (soundcard reader threads) + FLAC writer + fan-out tap
- teams-detect (pycaw, COM-MTA) and hotkey (Win32) threads
- tray + overlay
- on meeting start (auto-live): transcriber workers (system continuous, mic VAD-gated), diarizer worker, merger
- FastAPI/uvicorn server (started with the process; window attaches on demand)

faster-whisper (ctranslate2) and pyannote (torch) release the GIL during compute, so threads are adequate; if contention is severe the diarizer can move to a subprocess (future).

**Lifecycle:** meeting start -> recording + brain start. Meeting end -> recording stops, FLAC finalised, brain torn down, sidecars flushed, optional clean re-diarization pass. The capture core keeps running idle between meetings (your always-on recorder).

### CPU-contention strategy (the central risk: Iris Xe, no GPU, auto-live every meeting)
- VAD on both channels; whisper beam=1 on the system channel; mic worker VAD-gated.
- **Live whisper model defaults smaller** (latency) than the archive model (quality).
- Diarization on a relaxed cadence (default 90 s), tunable.
- **Transcription is prioritised; diarization may run behind** - the lag indicator shows it; Q&A is never blocked.
- `live_brain` config: `auto` (chosen) | `on-demand` | `off`; plus `live_diarization: true|false` to fall back to "live transcript now, diarize at meeting end" if the machine struggles. These knobs ship in v1 so no refactor is needed to dial back.

---

## Configuration (one file, superset of whisp-rec's)

Existing keys kept: `output_dir`, `samplerate`, `channels`, `format`, `subtype`, `hotkey`, `teams_*`, `overlay_*`, `auto_transcribe`, `transcribe_*`, `min_free_gb_warning`, `max_recording_minutes`.

New keys: `live_brain` (auto/on-demand/off), `live_diarization` (bool), `live_whisper_model` (default `small` - CPU-light; step up only if word accuracy too low), `live_whisper_beam` (1), `archive_whisper_model` (`large-v3-turbo`), `diarize_interval_s` (90), `diarize_window_s` (180), `diarize_threshold` (0.70), `claude_model` (`claude-sonnet-4-6`), `claude_model_heavy` (opus), `auto_open_window` (false), `hf_token` (or env `HF_TOKEN`), `anthropic_api_key` (or env).

---

## Failure modes

| Failure | Mitigation |
|---|---|
| CPU cannot keep diarization current (auto-live) | Transcript stays live; diarization runs behind; lag shown. Or `live_diarization: false` -> diarize at meeting end. |
| pyannote merges/splits a speaker | UI rename + merge; post-meeting full re-diarization. |
| No headphones -> mic re-captures remote audio | Documented assumption; VAD threshold; recommend headphones. |
| Audio device disappears (Bluetooth/sleep) | Existing whisp-rec capture retries; status surfaced. |
| Teams detect misses a muted/deafened call (no audio) | Manual hotkey start always works (existing behaviour). |
| Transcript exceeds model context | Prompt caching; rolling summary of older parts + recent verbatim (added if/when needed). |
| Claude/network error during Q&A | Error shown in chat + retry; recording/transcription unaffected. |
| Clock drift between channels over a long call | Single capture device pair (same clock); overlap-based attribution tolerates small drift. |
| Logon task points at old path after move | `install.ps1` repoints the `whisp-rec` task during migration; verify task state. |

---

## Privacy

Audio stays local. **Every meeting is archived to FLAC** (existing behaviour) - mind retention for confidential (Festo) calls. **Transcript text is sent to the Anthropic API** on each Q&A. A future local-LLM mode could remove that. Sidecars live next to the FLAC under `C:\recordings`.

---

## Prerequisites

- HuggingFace token + one-time acceptance of `pyannote/speaker-diarization-3.1` (+ `pyannote/segmentation-3.0`). Set `HF_TOKEN`.
- `ANTHROPIC_API_KEY`.
- Headphones.
- One consolidated venv (in the repo) adding to whisp-rec's deps: `faster-whisper`, `pyannote.audio`, `torch` (CPU), `fastapi`, `uvicorn[standard]`, `pywebview`, `anthropic`, `scipy`. Shares the HuggingFace model cache with `C:\Tools\whisper`.

---

## Migration plan (whisp-rec -> unified package)

1. Lift `recorder.py`, `teams_detect.py`, `tray.py`, `overlay.py`, `config.json`, `install.ps1` into `live-meeting-agent/lma/`.
2. Add the fan-out tap + bus; keep FLAC archive behaviour byte-identical.
3. Build the brain + server + UI around the bus.
4. Update `install.ps1` to create the consolidated repo venv and **repoint the Task Scheduler `whisp-rec` task** to the new entry point.
5. Verify recorder parity (hotkey, Teams detect, overlay, archive) before enabling the brain.
6. Archive (do not delete) the old `C:\Tools\whisp-rec` folder after parity is confirmed.

The `whisp` claude-hub skill and `C:\Tools\whisper` venv are left in place (independent ad-hoc transcription).

---

## Testing strategy

- **Unit:** ring buffer / bus; registry matching (synthetic embeddings -> stable ids, new-speaker at threshold); merger overlap-alignment; drawio extraction; qa prompt-building; config superset load.
- **Component (fixtures):** diarizer on a prepared stereo WAV with 2-3 known speakers -> speaker count + label stability across passes; live transcriber on a known WAV -> expected words.
- **Offline E2E (key enabler):** a **file-replay source** feeds an existing `C:\recordings` FLAC through the bus as if live -> `.transcript.jsonl` with speaker labels; a scripted "summarize" -> non-empty. Deterministic, no live meeting needed.
- **Capture parity:** smoke-test that the lifted recorder still produces an identical FLAC + the tap delivers audio to the bus.
- **Live Q&A test** gated on `ANTHROPIC_API_KEY`.

---

## Build sequence (incremental value)

| Milestone | Scope |
|---|---|
| **M0 - Lift + parity** | Move whisp-rec into `lma/`, consolidated venv, repoint logon task. Recorder behaves identically (hotkey, Teams detect, overlay, archive). Add the fan-out tap + bus (no consumer yet). |
| **M1 - Live transcript** | Brain transcriber (system + mic) + merger + `.transcript.jsonl`; FastAPI + pywebview window showing the live transcript over WS. Speakers = "You" vs "Remote" (no diarization yet). |
| **M2 - Reactive Q&A** | `qa.py` + chat UI + streamed replies + presets + drawio artifact. First genuinely useful build (You vs Remote). |
| **M3 - Rolling diarization** | `diarizer.py` + registry; split "Remote" into Speaker 1/2/3; legend rename/merge. The full ask. |
| **M4 - Auto-live + hardening** | Wire brain to the meeting lifecycle (auto-live), CPU-contention tuning + graceful degradation, post-meeting clean re-diarization, persistence/restore, `auto_transcribe` archive flag finally usable end-to-end. |

M0 protects the working recorder first; usable sparring partner by M2; full diarized auto-live by M4.

---

## Repo layout

```
live-meeting-agent/
├─ lma/                              # the unified package
│  ├─ app.py                         # entry: capture core + tray + server; brain per config
│  ├─ config.py / config.json        # unified config (superset of whisp-rec's)
│  ├─ capture/
│  │  ├─ recorder.py                 # soundcard capture -> FLAC + fan-out tap   (lifted)
│  │  ├─ bus.py                      # per-channel 16 kHz ring buffers           (new)
│  │  ├─ teams_detect.py             # pycaw meeting lifecycle                   (lifted)
│  │  ├─ tray.py                     # Win32 hotkey + tray menu                  (lifted)
│  │  └─ overlay.py                  # REC overlay                              (lifted)
│  ├─ brain/
│  │  ├─ transcriber.py  diarizer.py  merger.py  state.py  qa.py  lifecycle.py
│  ├─ server/
│  │  ├─ server.py  shell.py         # FastAPI + pywebview
│  │  └─ frontend/                   # Vite + React SPA (built -> static, served by FastAPI)
│  └─ transcription_batch.py         # post-meeting clean pass (reuses whisp engine)
├─ install.ps1                       # venv + repoint Task Scheduler
├─ tests/  (fixtures/, test_*.py)
├─ recordings -> C:\recordings\YYYY-MM\  # FLAC + sidecars: .transcript.jsonl, .speakers.json, .summary.md, artifacts\
├─ agent.py audio.py transcription.py llm.py drawio.py model.py   # EXISTING - shelved
├─ requirements.txt                  # capture + brain + server (one venv)
├─ docs/superpowers/specs/2026-06-07-sparring-partner-design.md
└─ CLAUDE.md                         # updated: unified package + shelved diagram tool
```

Output: keep `C:\recordings\YYYY-MM\YYMMDD_HHMMSS.flac`; live artifacts are **same-stem sidecars** (`.transcript.jsonl`, `.speakers.json`, `.summary.md`, `artifacts\`) so the archive layout barely changes. [Alternative: a per-meeting subfolder; chose sidecars to preserve current behaviour.]

---

## Assumptions

- [ASSUMPTION] pyannote 3.1 runs acceptably on this CPU at a 90 s cadence over ~3-min windows while whisper also runs live. Validate in M3/M4; tune cadence/window/threshold or set `live_diarization:false` if not.
- [ASSUMPTION] The fan-out tap adds negligible overhead to the existing capture loop. Validate in M0.
- [ASSUMPTION] A `small` live whisper model keeps up near-real-time on the system channel with beam=1 + VAD while pyannote runs, with word accuracy good enough for summaries (jargon secondary). Validate in M1/M4; step up to `medium` / `large-v3-turbo` only if word accuracy is too low and CPU headroom allows. Efficiency / low CPU is the priority.
- [ASSUMPTION] One consolidated venv can hold soundcard + faster-whisper + pyannote + torch + fastapi + pywebview without conflict. Validate in M0.
- [ASSUMPTION] Repointing the Task Scheduler task to the repo entry point keeps silent logon auto-start working. Validate in M0.

---

## Non-goals (v1)

- Real participant names (generic speakers; rename manually).
- Teams / Graph / bot-framework integration.
- Sub-second live diarization (cadence-based).
- Spoken (TTS) replies, wake-word control.
- Cross-meeting speaker recognition.
- Remote / multi-user access (localhost only).
- Embedding the old deterministic drawio renderer (a "draw it" command emits drawio XML directly).
- Multiple simultaneous recordings (single-instance, as today).

## Future / out of scope

- TTS replies, wake-word.
- Cross-meeting voice registry ("same person as last week").
- Local-only LLM mode for confidential calls.
- Rolling-summary context compression for multi-hour meetings.
- Reuse of the shelved deterministic drawio renderer for layout-stable diagrams.
- Auto periodic summaries pushed into chat unprompted.
