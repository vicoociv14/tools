"""Azure Speech streaming STT backend - the cloud alternative to the local whisper Brain.

Same interface as `Brain` (attach/start/stop) so `LiveSession` can pick either.
Subscribes to the AudioBus and pushes 16 kHz mono PCM into Azure Speech in real
time:
  mic    -> SpeechRecognizer       -> speaker "You"
  system -> ConversationTranscriber -> "Speaker 1/2/3" (diarization), or "Remote"

Continuous DE/EN language ID. Recognized events become Segments via the shared
Merger, so the transcript / jsonl / WebSocket path is byte-identical to whisper.
Because recognition runs in Azure's cloud and streams results back in ~1-2 s, the
delay does not grow with meeting length the way the local CPU path did.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

import numpy as np
import azure.cognitiveservices.speech as speechsdk

from ..capture.bus import AudioBus
from .merger import Merger
from .state import Segment, Transcript

log = logging.getLogger(__name__)

TICKS_PER_SECOND = 10_000_000  # Azure offset/duration are 100-ns ticks


def _to_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    return (clipped * 32767.0).astype("<i2").tobytes()


class _ChannelStream:
    """One Azure recognizer fed by a push stream, emitting Segments for one channel."""

    def __init__(
        self,
        channel: str,
        on_segment: Callable[[Segment], None],
        speech_config: "speechsdk.SpeechConfig",
        languages: list,
        diarize: bool,
        fixed_speaker: str,
        speaker_map: dict,
    ):
        self.channel = channel
        self.on_segment = on_segment
        self.diarize = diarize
        self.fixed_speaker = fixed_speaker
        self.speaker_map = speaker_map  # shared dict: azure speaker_id -> "Speaker N"

        fmt = speechsdk.audio.AudioStreamFormat(samples_per_second=16000, bits_per_sample=16, channels=1)
        self.push = speechsdk.audio.PushAudioInputStream(stream_format=fmt)
        audio_config = speechsdk.audio.AudioConfig(stream=self.push)
        auto = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(languages=list(languages))

        if diarize:
            self.recognizer = speechsdk.transcription.ConversationTranscriber(
                speech_config=speech_config,
                audio_config=audio_config,
                auto_detect_source_language_config=auto,
            )
            self.recognizer.transcribed.connect(self._on_result)
        else:
            self.recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config,
                auto_detect_source_language_config=auto,
            )
            self.recognizer.recognized.connect(self._on_result)
        self.recognizer.canceled.connect(self._on_canceled)

    def _speaker_for(self, result) -> str:
        if not self.diarize:
            return self.fixed_speaker
        sid = getattr(result, "speaker_id", None) or "Unknown"
        if sid in ("Unknown", "", None):
            return self.fixed_speaker  # not yet attributed -> "Remote"
        label = self.speaker_map.get(sid)
        if label is None:
            label = f"Speaker {len(self.speaker_map) + 1}"
            self.speaker_map[sid] = label
        return label

    def _on_result(self, evt) -> None:
        r = evt.result
        if r.reason != speechsdk.ResultReason.RecognizedSpeech or not r.text:
            return
        start = r.offset / TICKS_PER_SECOND
        end = (r.offset + r.duration) / TICKS_PER_SECOND
        try:
            self.on_segment(Segment(start=start, end=end, text=r.text,
                                    speaker=self._speaker_for(r), channel=self.channel))
        except Exception:
            log.exception("azure %s on_segment failed", self.channel)

    def _on_canceled(self, evt) -> None:
        log.warning("azure %s canceled: reason=%s details=%s",
                    self.channel, evt.reason, getattr(evt, "error_details", ""))

    def feed(self, samples: np.ndarray) -> None:
        try:
            self.push.write(_to_pcm16(samples))
        except Exception:
            log.debug("azure %s push.write failed", self.channel, exc_info=True)

    def start(self) -> None:
        if self.diarize:
            self.recognizer.start_transcribing_async().get()
        else:
            self.recognizer.start_continuous_recognition_async().get()

    def stop(self) -> None:
        try:
            if self.diarize:
                self.recognizer.stop_transcribing_async().get()
            else:
                self.recognizer.stop_continuous_recognition_async().get()
        except Exception:
            log.debug("azure %s stop raised", self.channel, exc_info=True)
        try:
            self.push.close()
        except Exception:
            log.debug("azure %s push.close raised", self.channel, exc_info=True)


class AzureBrain:
    """Drop-in replacement for Brain that transcribes via Azure Speech streaming."""

    def __init__(
        self,
        bus: AudioBus,
        transcript: Transcript,
        *,
        broadcast: Optional[Callable[[Segment], None]] = None,
        key: str,
        region: str = "swedencentral",
        languages=("de-DE", "en-US"),
        diarize_system: bool = True,
    ):
        if not key:
            raise RuntimeError("AzureBrain requires a Speech resource key")
        self.bus = bus
        self.merger = Merger(transcript, broadcast)

        speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
        # Continuous language ID so DE<->EN switches mid-meeting are tracked,
        # instead of locking to whatever language the first utterance was.
        speech_config.set_property(
            speechsdk.PropertyId.SpeechServiceConnection_LanguageIdMode, "Continuous"
        )

        langs = list(languages)
        self._speaker_map: dict = {}
        self.mic = _ChannelStream("mic", self.merger.on_segment, speech_config, langs,
                                  diarize=False, fixed_speaker="You", speaker_map=self._speaker_map)
        self.system = _ChannelStream("system", self.merger.on_segment, speech_config, langs,
                                     diarize=diarize_system, fixed_speaker="Remote",
                                     speaker_map=self._speaker_map)
        self._by_channel = {"mic": self.mic, "system": self.system}

    def attach(self) -> None:
        self.bus.subscribe(self._dispatch)

    def _dispatch(self, channel: str, samples: np.ndarray) -> None:
        ch = self._by_channel.get(channel)
        if ch is not None:
            ch.feed(samples)

    def start(self) -> None:
        self.mic.start()
        self.system.start()

    def stop(self) -> None:
        self.mic.stop()
        self.system.stop()
