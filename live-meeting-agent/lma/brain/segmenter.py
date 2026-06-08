from __future__ import annotations

import numpy as np


def find_utterance_end(
    audio: np.ndarray,
    sample_rate: int,
    *,
    silence_rms: float = 0.005,
    min_silence_s: float = 0.6,
    min_speech_s: float = 0.4,
    max_utterance_s: float = 20.0,
    frame_s: float = 0.05,
) -> int | None:
    """Return the sample index where a complete utterance ends, or None.

    Scan in `frame_s` frames. Once at least `min_speech_s` of speech (frame RMS
    >= `silence_rms`) has accumulated AND `min_silence_s` of trailing silence is
    seen, cut at the end of the last speech frame. If the buffer reaches
    `max_utterance_s` with enough speech but no pause, force a cut at the end
    (bounds latency).
    """
    n = len(audio)
    if n == 0:
        return None
    frame = max(1, int(sample_rate * frame_s))
    min_speech = int(min_speech_s * sample_rate)
    min_silence = int(min_silence_s * sample_rate)
    speech_samples = 0
    silence_run = 0
    last_speech_end = 0
    for start in range(0, n - frame + 1, frame):
        chunk = audio[start:start + frame]
        rms = float(np.sqrt(np.mean(chunk * chunk)))
        if rms >= silence_rms:
            speech_samples += frame
            silence_run = 0
            last_speech_end = start + frame
        else:
            silence_run += frame
            if speech_samples >= min_speech and silence_run >= min_silence:
                return last_speech_end
    if n >= int(max_utterance_s * sample_rate) and speech_samples >= min_speech:
        return n
    return None
