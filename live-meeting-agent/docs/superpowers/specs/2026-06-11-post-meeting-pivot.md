# M7 - Post-meeting transcription pivot (2026-06-11)

**Decision:** remove the entire live/real-time pipeline (live window, live chat, streaming STT) and replace it with a post-meeting batch transcription. Requested by Vico: the live chat was never used, and real-time transcription produced misordered text. The product is now: **record -> transcribe perfectly after the meeting -> Meeting Archive** (transcript + metadata: timestamp, title, summary, topics, speakers; search; per-meeting chat; export).

## Why batch fixes the live problems
- **Ordering:** the live pipeline cut mic/system into utterances independently and merged on arrival (two clocks). Batch transcribes the finished file on one timeline - ordering is correct by construction.
- **Accuracy:** Azure's batch model with full-file context beats streaming partials; full sentences + punctuation.
- **Speaker separation:** diarization over the whole file (verified: 5 speakers distinguished on a real meeting).

## Engine: Azure Speech fast transcription (batch REST)
- `POST {speech_stt_endpoint}/speechtotext/transcriptions:transcribe?api-version=2024-11-15`, multipart `audio` + `definition`.
- Endpoint `https://vstr-mq4q2wgo-swedencentral.cognitiveservices.azure.com` - same resource + key as Claude/Foundry (`LMA_FOUNDRY_API_KEY`).
- ~60x realtime (24 min -> ~25 s). Locales `de-DE`/`en-US` identified per phrase.
- Stereo handling: channel 0 (mic) transcribed without diarization -> "You"; channel 1 (system) with `diarization {maxSpeakers}` -> "Speaker 1..N" (normalized by first appearance). Channels can't be combined with diarization in one request, hence two requests.
- Limits: diarization < 2 h per file (fallback: "Remote"); silent channel -> HTTP 422 `NoLanguageIdentified` (= no speech); file < 500 MB.

## Flow
tray `_stop` -> duration < 15 s? delete : spawn `python -m lma.post <flac>` (detached pythonw)
-> extract channels -> 2x fast transcription -> merge sorted by start -> `<id>.transcript.jsonl`
-> trivial? (<=10 segments and short) delete all : drop stale meta -> titler (Claude) -> `<id>.meta.json` -> appears in archive.

## Removed
LiveSession, TranscriptHub, live FastAPI app (`/api/transcript`, `/ws`, live `/api/ask`), `lma/ui.py`, `lma/serve.py`, AudioBus + recorder tap consumer, replay, streaming AzureBrain, whisper_engine, openai_stt, live React app (index.html/App/Chat/useTranscript/useAsk), config keys (`live_*`, `server_port`, `ui_auto_open`, `auto_transcribe`, `transcribe_*`, `openai_*`), deps (faster-whisper, azure-cognitiveservices-speech SDK, openai, scipy). Tray menu: "Open Live Agent" removed; "Open Meeting Archive" stays.

## Kept
Capture core (recorder/teams detect/overlay/hotkey/discard), `state.py` + `qa.py` (archive chat + titler), `shell.py` (archive window), Meeting Archive (M6) incl. export, persisted auto-record toggle, no-Quit tray.
