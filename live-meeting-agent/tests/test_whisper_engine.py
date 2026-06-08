import os
import numpy as np
import pytest

# Real-model test: opt in with RUN_WHISPER=1 (downloads the 'small' model on first run).
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_WHISPER") != "1",
    reason="set RUN_WHISPER=1 to run the real faster-whisper test",
)


def test_transcribe_silence_returns_list():
    from lma.brain.whisper_engine import transcribe_array
    audio = np.zeros(16000, dtype=np.float32)  # 1 s silence
    result = transcribe_array(audio, 16000)
    assert isinstance(result, list)  # silence -> usually empty, must not error


def test_rejects_non_16k():
    from lma.brain.whisper_engine import transcribe_array
    with pytest.raises(ValueError):
        transcribe_array(np.zeros(8000, dtype=np.float32), 8000)
