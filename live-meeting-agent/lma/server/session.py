"""LiveSession - the in-tray live brain + server + UI window for one meeting.

Wired into the always-on tray (lma.capture.tray): on recording start the tray
sets the recorder's tap to this session's bus and calls `start(path)`; on stop
it calls `stop()`. Everything here is best-effort - a failure must never break
the recorder (the tray wraps the calls in try/except, and the fan-out tap itself
swallows errors).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from ..brain.brain import Brain
from ..brain.state import Transcript
from ..brain.whisper_engine import make_transcribe_fn
from ..capture.bus import AudioBus
from .hub import TranscriptHub
from .server import create_app
from .shell import ServerThread

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"


class LiveSession:
    """Owns one meeting's AudioBus, Brain, FastAPI server and UI window process."""

    def __init__(self, config: dict, transcribe_fn=None):
        self.config = config
        self.bus = AudioBus(
            source_samplerate=int(config.get("samplerate", 48000)),
            capacity_seconds=3600,
        )
        self._transcribe_fn = transcribe_fn  # injectable for tests
        self.port = int(config.get("server_port", 8731))
        self.brain = None
        self.server = None
        self.ui_proc = None

    def start(self, recording_path: Path) -> None:
        jsonl = Path(recording_path).with_suffix(".transcript.jsonl")
        transcript = Transcript(jsonl_path=jsonl)
        hub = TranscriptHub()
        self.brain = self._build_brain(transcript, hub)
        self.brain.attach()
        self.brain.start()

        app = create_app(transcript, hub, static_dir=FRONTEND_DIST, config=self.config)
        self.server = ServerThread(app, port=self.port)
        self.server.start()

        if self.config.get("ui_auto_open", True):
            self._spawn_ui()
        log.info("live session started -> %s (port %d)", jsonl, self.port)

    def _build_brain(self, transcript: Transcript, hub: TranscriptHub):
        """Build the live transcription backend:
          azure_speech      -> AzureBrain (cloud streaming STT + diarization)
          openai_transcribe -> Brain + cloud gpt-4o-transcribe transcribe_fn
          whisper           -> Brain + local faster-whisper (offline fallback)
        An injected transcribe_fn (tests) forces the local Brain path."""
        backend = str(self.config.get("live_stt_backend", "whisper")).lower()
        if backend == "azure_speech" and self._transcribe_fn is None:
            try:
                from ..brain.azure_stt import AzureBrain
                key = os.environ.get("LMA_SPEECH_KEY") or os.environ.get("LMA_FOUNDRY_API_KEY")
                if not key:
                    raise RuntimeError("azure_speech needs LMA_SPEECH_KEY / LMA_FOUNDRY_API_KEY")
                return AzureBrain(
                    self.bus, transcript, broadcast=hub.publish, key=key,
                    region=self.config.get("speech_region", "swedencentral"),
                    languages=tuple(self.config.get("speech_languages", ["de-DE", "en-US"])),
                    diarize_system=bool(self.config.get("speech_diarize", True)),
                )
            except Exception:
                log.exception("azure_speech backend setup failed; falling back")
        return Brain(self.bus, transcript, self._pick_transcribe_fn(), broadcast=hub.publish)

    def _pick_transcribe_fn(self):
        if self._transcribe_fn is not None:
            return self._transcribe_fn  # test injection
        backend = str(self.config.get("live_stt_backend", "whisper")).lower()
        if backend == "openai_transcribe":
            try:
                from ..brain.openai_stt import make_openai_transcribe_fn
                key = os.environ.get("LMA_FOUNDRY_API_KEY") or os.environ.get("LMA_SPEECH_KEY")
                endpoint = self.config.get("openai_endpoint")
                deployment = self.config.get("openai_transcribe_deployment")
                if not (key and endpoint and deployment):
                    raise RuntimeError(
                        "openai_transcribe needs LMA_FOUNDRY_API_KEY + openai_endpoint "
                        "+ openai_transcribe_deployment"
                    )
                return make_openai_transcribe_fn(
                    endpoint=endpoint, api_key=key, deployment=deployment,
                    api_version=self.config.get("openai_api_version", "2025-03-01-preview"),
                    language=self.config.get("live_whisper_lang") or None,
                )
            except Exception:
                log.exception("openai_transcribe setup failed; falling back to whisper")
        return make_transcribe_fn(
            self.config.get("live_whisper_lang") or None,
            self.config.get("live_whisper_model", "small"),
        )

    def _spawn_ui(self) -> None:
        pyw = REPO_ROOT / ".venv" / "Scripts" / "pythonw.exe"
        exe = str(pyw) if pyw.exists() else sys.executable
        try:
            self.ui_proc = subprocess.Popen(
                [exe, "-m", "lma.ui", "--port", str(self.port)],
                cwd=str(REPO_ROOT),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            log.exception("failed to spawn UI window")

    def stop(self) -> None:
        if self.ui_proc is not None:
            try:
                self.ui_proc.terminate()
            except Exception:
                log.debug("ui terminate failed", exc_info=True)
            self.ui_proc = None
        # Stop the server BEFORE the brain: brain.stop() can block on an in-flight
        # whisper utterance, and we want the port (8731) freed fast so a quick
        # re-join can rebind it.
        if self.server is not None:
            try:
                self.server.stop()
            except Exception:
                log.exception("server stop failed")
            self.server = None
        if self.brain is not None:
            try:
                self.brain.stop()
            except Exception:
                log.exception("brain stop failed")
            self.brain = None
