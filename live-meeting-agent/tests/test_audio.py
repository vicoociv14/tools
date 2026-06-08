import numpy as np
from audio import RingBuffer


def test_ring_buffer_basic_write_read():
    buf = RingBuffer(capacity_seconds=2, sample_rate=16000)
    chunk = np.ones(8000, dtype=np.float32)
    buf.write(chunk)
    out = buf.read_since(0.0)
    assert len(out) == 8000


def test_ring_buffer_overwrites_oldest():
    buf = RingBuffer(capacity_seconds=1, sample_rate=16000)
    buf.write(np.ones(20000, dtype=np.float32))  # 1.25s of audio in 1s buffer
    out = buf.read_since(0.0)
    assert len(out) == 16000  # capped at capacity
