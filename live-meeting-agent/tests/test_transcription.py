from pathlib import Path
import pytest
import numpy as np
from transcription import transcribe_array

WAV = Path(__file__).parent / "fixtures" / "test_speech.wav"
pytestmark = pytest.mark.skipif(not WAV.exists(), reason="missing fixture WAV")


def test_transcribe_array_returns_text():
    import wave
    with wave.open(str(WAV)) as f:
        frames = f.readframes(f.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        sr = f.getframerate()
    text = transcribe_array(audio, sr)
    assert "test" in text.lower() or "transcription" in text.lower()
