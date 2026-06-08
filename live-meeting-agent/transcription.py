import threading
import time
import numpy as np
from faster_whisper import WhisperModel
from audio import RingBuffer
from model import TranscriptSegment

DEFAULT_MODEL_SIZE = "medium.en"
CHUNK_SECONDS = 30


_model_cache: WhisperModel | None = None


def _model() -> WhisperModel:
    global _model_cache
    if _model_cache is None:
        _model_cache = WhisperModel(DEFAULT_MODEL_SIZE, device="auto", compute_type="auto")
    return _model_cache


def transcribe_array(audio: np.ndarray, sample_rate: int) -> str:
    if sample_rate != 16000:
        from scipy import signal
        audio = signal.resample_poly(audio, 16000, sample_rate).astype(np.float32)
    segments, _ = _model().transcribe(audio, language="en", vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


class TranscriptionThread(threading.Thread):
    def __init__(self, ring: RingBuffer, sink: list[TranscriptSegment]):
        super().__init__(daemon=True)
        self.ring = ring
        self.sink = sink
        self.sink_lock = threading.Lock()
        self.stop_flag = threading.Event()

    def run(self):
        while not self.stop_flag.is_set():
            time.sleep(CHUNK_SECONDS)
            audio = self.ring.read_since(CHUNK_SECONDS)
            if len(audio) < self.ring.sample_rate:  # less than 1 second
                continue
            try:
                text = transcribe_array(audio, self.ring.sample_rate)
            except Exception as exc:  # pragma: no cover
                print(f"transcription: error {exc!r}")
                continue
            if text:
                t = time.strftime("%H:%M:%S")
                with self.sink_lock:
                    self.sink.append(TranscriptSegment(t=t, text=text))

    def drain(self) -> list[TranscriptSegment]:
        with self.sink_lock:
            out = list(self.sink)
            self.sink.clear()
            return out

    def stop(self):
        self.stop_flag.set()
