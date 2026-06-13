# live-meeting-agent

Meeting recorder + archive at `C:\Repos\tools\live-meeting-agent`. An always-on tray records every Teams meeting (mic + system -> stereo FLAC). When the meeting ends, a background job transcribes the file via **Azure Speech fast transcription** (batch REST: accurate, ordered, diarized, DE/EN per phrase) and auto-titles it. The **Meeting Archive** window is the product: browse/search all meetings, read the speaker-attributed transcript, chat about it with Claude, export to .txt.

**There is no live/real-time pipeline anymore** (removed 2026-06-11 by design: unused, and real-time chunking caused misordered text).

## Status (2026-06-11)
- **Capture** (M0): record + Teams auto start/stop (window-based) + `Ctrl+Alt+R` + tray + REC overlay. LIVE via logon task `whisp-rec`.
- **Post-meeting transcription** (M7): `lma/post/` - on recording stop the tray spawns `python -m lma.post <flac>`: mic channel -> "You", system channel -> diarized "Speaker 1..N" (Azure fast transcription, ~60x realtime, <2 h files for diarization), writes `<id>.transcript.jsonl`, discards trivial recordings, then titles via Claude. Verified on real meetings (24 min -> 26 s; 5 speakers distinguished).
- **Meeting Archive** (M6): `python -m lma.archive` window (port 8732, tray menu "Open Meeting Archive") - list with auto title/summary/topics/date/duration, full transcript, search, per-meeting Claude chat, Export transcript (native Save As).
- **Discard guard**: recordings < `discard_max_seconds` deleted at stop; short recordings with <= `discard_max_segments` segments deleted after transcription.

## Run
    # AUTO: join a Teams call - it records; on hang-up the transcript+title appear in the archive.
    .\.venv\Scripts\python.exe -m lma.post "recordings\2026-06\<file>.flac"   # re/transcribe one recording
    .\.venv\Scripts\python.exe -m lma.archive                                  # archive window (or tray menu)
    .\.venv\Scripts\python.exe -m lma.archive.backfill                         # title all untitled meetings
    .\.venv\Scripts\python.exe -m lma.capture.tray                             # dev tray (stop the task first)
    .\.venv\Scripts\python.exe -m pytest tests\test_state.py tests\test_qa.py tests\test_discard.py tests\test_post.py tests\test_archive_index.py tests\test_archive_server.py -q

## Prereqs
- `LMA_FOUNDRY_API_KEY` (user env): one key for BOTH Azure fast transcription (Cognitive Services endpoint) and Claude (Foundry `/anthropic`) - same resource `vstr-mq4q2wgo-swedencentral`. Tray must be restarted after `setx` to inherit.

## Layout
- `run.pyw` - silent tray entry (logon task `whisp-rec`). `install.ps1` - venv + task registration.
- `lma/capture/` - recorder (stereo FLAC, L=mic R=system), teams_detect (window + audio fallback), tray (record + spawn post job + archive launcher), overlay, config.json.
- `lma/post/` - fast_stt.py (channel split -> 2 fast-transcription requests -> merge ordered segments), discard.py, `__main__.py` (job: transcribe -> jsonl -> sparse-discard -> title).
- `lma/brain/` - state.py (Segment/Transcript + jsonl), qa.py (Claude via Foundry: presets, prompt-cached transcript, streaming, drawio extract).
- `lma/archive/` - index.py (scan recordings -> MeetingMeta), titler.py (Claude title/summary/topics -> `<id>.meta.json`), server.py (FastAPI: meetings/detail/ask/search), `__main__.py` (pywebview window + native Save As export), backfill.py.
- `lma/server/shell.py` - uvicorn thread + pywebview window helper (used by archive).
- `lma/server/frontend/` - Vite + React, single page `archive.html` (built `dist` committed).
- `recordings/` (gitignored): `<id>.flac` + `<id>.transcript.jsonl` + `<id>.meta.json`.

## Config knobs (`lma/capture/config.json`)
- STT: `speech_stt_endpoint`, `speech_languages` (["de-DE","en-US"]), `speech_diarize`, `speech_max_speakers`.
- Q&A/titles: `qa_backend` (`foundry`|`anthropic`), `foundry_base_url`, `foundry_model`.
- Discard: `discard_trivial`, `discard_max_seconds` (15), `discard_max_segments` (10).
- Teams: `teams_detect_method` `window`|`audio`, poll/start/stop thresholds. `auto_record_enabled` is the persisted tray toggle.
- `archive_port` (8732).

## Gotchas
- One global hotkey: stop the scheduled task before running a dev tray.
- Tray menu has NO Quit (icon must always stay); full stop = `scripts\agent-off.ps1`, re-enable = `agent-on.ps1`.
- Azure fast transcription: diarization requires file < 2 h (job falls back to "Remote" labels beyond that); a silent channel returns HTTP 422 NoLanguageIdentified (handled as no speech).
- uvicorn under `pythonw` needs `log_config=None` (stderr is None) - already set in `lma/server/shell.py`.
- Two pythonw processes = ONE tray (venv launcher + interpreter child). Single instance enforced via `.whisp-rec.lock`.
- Built frontend `dist` is committed; rebuild with `cd lma\server\frontend; npm run build`.
- Shelved old drawio generator: `agent.py`, `llm.py`, `drawio.py`, `model.py`, old `audio.py`/`transcription.py` (+ their tests) - untouched, ignore.
