# live-meeting-agent

Active scribe that listens to a meeting and incrementally updates a `.drawio` file every 5 minutes (or on hotkey).

## Setup

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    set ANTHROPIC_API_KEY=sk-ant-...

The first run downloads the `medium.en` Whisper model (~1.5 GB) into the user cache.

## Run

Live mode (default 5-min interval, hotkey `Ctrl+Shift+U`):

    python agent.py my-meeting

Live mode with custom interval:

    python agent.py my-meeting --interval 90s

Batch mode (one-shot from a transcript file):

    python agent.py demo --transcript tests/fixtures/transcript_architecture.txt

Open `meetings/<name>/meeting.drawio` in any drawio viewer (VS Code drawio extension, drawio desktop, or app.diagrams.net) and screen-share that window in Teams.

## Output structure

    meetings/<name>/
    +- meeting.drawio    # multi-page: live page per type, snapshots, archived
    +- state.json        # current JSON model (resume from where you left off)

## Tests

    pytest                                  # unit tests
    pytest tests/test_llm_golden.py         # LLM golden tests (needs ANTHROPIC_API_KEY)

## Architecture

See `docs/superpowers/specs/2026-04-26-live-meeting-agent-design.md`.
