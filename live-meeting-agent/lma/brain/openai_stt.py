"""OpenAI gpt-4o-transcribe backend - a cloud transcribe_fn that drops into the
existing Brain/ChannelTranscriber pipeline (no architecture change).

The local faster-whisper path can't keep up with two channels of continuous
speech on a low-power CPU, so the delay grows for the whole meeting. Sending each
cut utterance to gpt-4o-transcribe on Azure Foundry instead means transcription
runs in the cloud in ~1-2 s and never falls behind: the delay stays bounded
(utterance length + round-trip), and DE/EN are auto-detected by the model.

make_openai_transcribe_fn(...) returns a TranscribeFn:
    (audio_16k_mono_float32, sr) -> [(0.0, duration_s, text)]
so mic stays "You" and system stays "Remote" via the existing channel split.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)


def make_openai_transcribe_fn(
    endpoint: str,
    api_key: str,
    deployment: str,
    *,
    api_version: str = "2025-03-01-preview",
    language: Optional[str] = None,  # None = let the model auto-detect (DE/EN)
):
    """Return a TranscribeFn that transcribes one utterance via Azure OpenAI
    gpt-4o-transcribe (chunked /audio/transcriptions). `deployment` is the Azure
    deployment name, `endpoint` the resource endpoint (e.g.
    https://<resource>.openai.azure.com or https://<resource>.services.ai.azure.com)."""
    import soundfile as sf  # lazy
    from openai import AzureOpenAI  # lazy

    client = AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)

    def _fn(audio: np.ndarray, sr: int) -> list:
        if audio is None or len(audio) == 0:
            return []
        buf = io.BytesIO()
        sf.write(buf, np.asarray(audio, dtype=np.float32), sr, format="WAV", subtype="PCM_16")
        buf.seek(0)
        kwargs = {"model": deployment, "file": ("utterance.wav", buf, "audio/wav")}
        if language:
            kwargs["language"] = language
        try:
            resp = client.audio.transcriptions.create(**kwargs)
        except Exception:
            log.exception("gpt-4o-transcribe request failed")
            return []
        text = (getattr(resp, "text", "") or "").strip()
        if not text:
            return []
        return [(0.0, len(audio) / sr, text)]

    return _fn
