# live-meeting-agent

Unified Live Meeting Agent at `C:\Tools\live-meeting-agent`. An always-on tray records every Teams meeting (mic + system -> stereo FLAC) and, when a call starts, **auto-launches a live brain + desktop window**: a live speaker-attributed transcript plus a Claude Q&A "sparring partner".

## Status (2026-06-08)
- **M0** capture core (lifted from whisp-rec): record + Teams auto start/stop (window-based) + `Ctrl+Alt+R` hotkey + tray + REC overlay. LIVE via logon task `whisp-rec`.
- **M1** live transcript: mic = "You", system = "Remote", chunked faster-whisper (`small`) -> `<recording>.transcript.jsonl`, streamed to a Vite/React UI over WebSocket in a pywebview window.
- **M2** Q&A: chat panel - presets (Summary / Decisions / Action items / Open questions / Draw drawio) + free text -> Claude (`claude-sonnet-4-6`), streamed, grounded in the transcript, replies in DE or EN.
- **M4** auto-live: the tray auto-starts the brain + server and opens the window on meeting start, tears down on end. `live_brain: auto`. Failure-isolated - it can never break recording.
- **M3 (remaining)** real diarization Speaker 1/2/3 via pyannote - needs a HuggingFace token; not built yet.

## Run
    # AUTO: just join a Teams call - the tray opens the transcript window itself.
    .\.venv\Scripts\python.exe -m lma.serve --source "recordings\<...>.flac"   # manual replay into the UI
    .\.venv\Scripts\python.exe -m lma.serve --source live                       # manual live session (no tray)
    .\.venv\Scripts\python.exe -m lma.capture.tray                              # dev tray (console; stop the task first)
    .\.venv\Scripts\python.exe -m pytest tests\test_bus.py tests\test_state.py tests\test_segmenter.py tests\test_transcriber.py tests\test_brain.py tests\test_hub.py tests\test_server.py tests\test_qa.py tests\test_session.py -q

## Prereqs
- `ANTHROPIC_API_KEY` (user env) for Q&A: `setx ANTHROPIC_API_KEY "sk-ant-..."`, then restart the tray/logon so the task inherits it. The transcript works without it.
- HF token (future M3) for pyannote.

## Layout
- `run.pyw` - silent tray entry (logon task `whisp-rec`). `install.ps1` - venv + task registration.
- `lma/capture/` - recorder (+ `tap`/`set_tap`), teams_detect (window + audio fallback), tray (auto-live wiring), overlay, bus (16 kHz fan-out + subscribe), config.json.
- `lma/brain/` - state (Segment/Transcript + jsonl), segmenter (silence cut), transcriber (per channel), merger, brain (orchestrator), whisper_engine (faster-whisper), qa (Claude Q&A).
- `lma/server/` - hub (thread->async), server (FastAPI: `/api/transcript`, `/api/ask`, `/ws/transcript`, static), shell (uvicorn thread + pywebview), session (LiveSession: bus+brain+server+UI per meeting), frontend/ (Vite + React; built `dist` committed).
- `lma/serve.py` (manual launch), `lma/ui.py` (pywebview window process the tray spawns).
- `recordings/` (gitignored): `<...>.flac` + `<...>.transcript.jsonl`.

## Config knobs (`lma/capture/config.json`)
- `live_brain`: `auto` | `on` | `off` (auto = brain + window every meeting). `ui_auto_open`: pop the window automatically (else use tray "Open live transcript"). `live_whisper_model` (`small`), `live_whisper_lang` (`null` = auto; DE/EN detected per utterance), `server_port` (8731).
- Teams: `teams_detect_method` `window`|`audio`, poll/start/stop thresholds.

## Gotchas
- One global hotkey + one server port: stop the scheduled task before running a dev `tray`/`serve`.
- numpy pinned `< 2.0`. `tests/` also holds the shelved diagram tests (they import removed deps) - run the specific `test_*.py` listed above.
- Built frontend `dist` is committed (un-ignored in `.gitignore`) so the UI runs without `npm run build`; rebuild with `cd lma\server\frontend; npm run build`.
- pywebview window and the pystray tray can't share one process -> the window runs as a separate `lma.ui` process the tray launches.
- Shelved old drawio generator: `agent.py`, `llm.py`, `drawio.py`, `model.py`, old `audio.py`/`transcription.py` (untouched).
