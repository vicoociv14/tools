import numpy as np
from lma.brain.segmenter import find_utterance_end

SR = 16000


def _speech(seconds, level=0.2):
    return np.full(int(seconds * SR), level, dtype=np.float32)


def _silence(seconds):
    return np.zeros(int(seconds * SR), dtype=np.float32)


def test_all_silence_returns_none():
    assert find_utterance_end(_silence(2.0), SR) is None


def test_speech_then_silence_cuts_after_speech():
    audio = np.concatenate([_speech(1.0), _silence(0.8)])
    cut = find_utterance_end(audio, SR)
    assert cut is not None
    assert abs(cut - SR) <= int(0.1 * SR)


def test_speech_without_trailing_silence_returns_none():
    audio = _speech(1.0)
    assert find_utterance_end(audio, SR) is None


def test_too_short_speech_ignored():
    audio = np.concatenate([_speech(0.2), _silence(0.8)])
    assert find_utterance_end(audio, SR) is None


def test_force_cut_at_max_utterance():
    audio = _speech(21.0)
    cut = find_utterance_end(audio, SR)
    assert cut == len(audio)
