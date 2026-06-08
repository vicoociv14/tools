from __future__ import annotations

import logging
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

_model = None
_model_size: Optional[str] = None


def _get_model(model_size: str, device: str = "cpu", compute_type: str = "int8"):
    global _model, _model_size
    if _model is None or _model_size != model_size:
        from faster_whisper import WhisperModel  # lazy: keep import cost off unit tests
        log.info("loading faster-whisper model '%s' (%s/%s)", model_size, device, compute_type)
        _model = WhisperModel(model_size, device=device, compute_type=compute_type)
        _model_size = model_size
    return _model


def transcribe_array(
    audio: np.ndarray,
    sample_rate: int,
    *,
    language: Optional[str] = None,
    model_size: str = "small",
) -> list:
    """Transcribe a 16 kHz mono float32 clip -> [(start_s, end_s, text), ...]."""
    if sample_rate != 16000:
        raise ValueError(f"expected 16 kHz audio, got {sample_rate}")
    model = _get_model(model_size)
    segments, _info = model.transcribe(audio, language=language, beam_size=1, vad_filter=True)
    out = []
    for s in segments:
        text = s.text.strip()
        if text:
            out.append((float(s.start), float(s.end), text))
    return out


def make_transcribe_fn(language: Optional[str] = None, model_size: str = "small"):
    """Return a TranscribeFn bound to a language/model, for ChannelTranscriber/Brain."""
    def _fn(audio, sr):
        return transcribe_array(audio, sr, language=language, model_size=model_size)
    return _fn
