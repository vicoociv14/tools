import threading
import time
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


class RingBuffer:
    def __init__(self, capacity_seconds: float, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.capacity = int(capacity_seconds * sample_rate)
        self.buffer = np.zeros(self.capacity, dtype=np.float32)
        self.write_pos = 0
        self.total_written = 0
        self.lock = threading.Lock()

    def write(self, chunk: np.ndarray) -> None:
        with self.lock:
            n = len(chunk)
            if n >= self.capacity:
                self.buffer[:] = chunk[-self.capacity:]
                self.write_pos = 0
                self.total_written += n
                return
            end = self.write_pos + n
            if end <= self.capacity:
                self.buffer[self.write_pos:end] = chunk
            else:
                first = self.capacity - self.write_pos
                self.buffer[self.write_pos:] = chunk[:first]
                self.buffer[:n - first] = chunk[first:]
            self.write_pos = (self.write_pos + n) % self.capacity
            self.total_written += n

    def read_since(self, seconds_ago: float) -> np.ndarray:
        with self.lock:
            samples = min(int(seconds_ago * self.sample_rate) if seconds_ago else self.capacity, self.total_written, self.capacity)
            if samples == 0:
                return np.zeros(0, dtype=np.float32)
            start = (self.write_pos - samples) % self.capacity
            if start + samples <= self.capacity:
                return self.buffer[start:start + samples].copy()
            return np.concatenate([self.buffer[start:], self.buffer[:samples - (self.capacity - start)]])


def find_loopback_device() -> int | None:
    """Return the device index of a WASAPI loopback for the default output."""
    hostapis = sd.query_hostapis()
    wasapi_idx = next((i for i, h in enumerate(hostapis) if h["name"] == "Windows WASAPI"), None)
    if wasapi_idx is None:
        return None
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d["hostapi"] == wasapi_idx and d["max_input_channels"] > 0 and "loopback" in d["name"].lower():
            return i
    default_out = sd.query_hostapis(wasapi_idx)["default_output_device"]
    return default_out


class CaptureThread(threading.Thread):
    def __init__(self, ring: RingBuffer):
        super().__init__(daemon=True)
        self.ring = ring
        self.stop_flag = threading.Event()

    def run(self):
        while not self.stop_flag.is_set():
            try:
                device = find_loopback_device()
                with sd.InputStream(
                    device=device,
                    samplerate=self.ring.sample_rate,
                    channels=1,
                    dtype="float32",
                    extra_settings=sd.WasapiSettings(loopback=True),
                    callback=self._callback,
                ):
                    while not self.stop_flag.is_set():
                        time.sleep(0.1)
            except Exception as exc:  # pragma: no cover - hardware errors
                print(f"audio: capture error {exc!r}, retrying in 5s")
                time.sleep(5)

    def _callback(self, indata, frames, t, status):  # pragma: no cover - sounddevice callback
        if status:
            print(f"audio: status {status}")
        self.ring.write(indata[:, 0].copy())

    def stop(self):
        self.stop_flag.set()
