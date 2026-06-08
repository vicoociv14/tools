import numpy as np
import pytest

from lma.capture.bus import AudioBus, RingBuffer


def test_ringbuffer_read_last_returns_recent_samples():
    rb = RingBuffer(capacity_seconds=1, sample_rate=16000)
    rb.write(np.arange(8000, dtype=np.float32))
    out = rb.read_last(0.25)  # last 0.25 s = 4000 samples
    assert len(out) == 4000
    assert out[-1] == 7999.0


def test_ringbuffer_overwrites_oldest_when_full():
    rb = RingBuffer(capacity_seconds=1, sample_rate=16000)
    rb.write(np.ones(20000, dtype=np.float32))  # 1.25 s into a 1 s buffer
    out = rb.read_last(10.0)  # ask for more than capacity
    assert len(out) == 16000  # capped at capacity


def test_bus_target_samplerate_is_16k():
    bus = AudioBus(source_samplerate=48000, capacity_seconds=2)
    assert bus.target_samplerate == 16000


def test_bus_push_splits_channels_and_downsamples():
    bus = AudioBus(source_samplerate=48000, capacity_seconds=2)
    n = 48000  # 1 s at 48 kHz
    frame = np.empty((n, 2), dtype=np.float32)
    frame[:, 0] = 0.5   # mic channel
    frame[:, 1] = -0.5  # system channel
    bus.push(frame)
    mic = bus.read_last("mic", 1.0)
    sysd = bus.read_last("system", 1.0)
    assert abs(len(mic) - 16000) <= 4   # ~1 s at 16 kHz
    assert abs(len(sysd) - 16000) <= 4
    assert mic.mean() == pytest.approx(0.5, abs=0.05)
    assert sysd.mean() == pytest.approx(-0.5, abs=0.05)


def test_bus_passthrough_when_source_is_16k():
    bus = AudioBus(source_samplerate=16000, capacity_seconds=2)
    frame = np.zeros((1600, 2), dtype=np.float32)
    frame[:, 0] = 1.0
    bus.push(frame)
    mic = bus.read_last("mic", 0.1)
    assert len(mic) == 1600
    assert mic.mean() == pytest.approx(1.0, abs=1e-6)


def test_bus_read_unknown_channel_raises():
    bus = AudioBus(source_samplerate=48000, capacity_seconds=2)
    with pytest.raises(ValueError):
        bus.read_last("nope", 1.0)


def test_bus_subscribe_receives_both_channels():
    bus = AudioBus(source_samplerate=16000, capacity_seconds=2)
    got = []
    bus.subscribe(lambda channel, samples: got.append((channel, len(samples))))
    frame = np.zeros((1600, 2), dtype=np.float32)
    bus.push(frame)
    channels = {c for c, _ in got}
    assert channels == {"mic", "system"}
    assert all(n == 1600 for _, n in got)


def test_bus_subscriber_error_does_not_break_push():
    bus = AudioBus(source_samplerate=16000, capacity_seconds=2)
    bus.subscribe(lambda channel, samples: (_ for _ in ()).throw(RuntimeError("boom")))
    frame = np.zeros((1600, 2), dtype=np.float32)
    bus.push(frame)  # must not raise
    assert len(bus.read_last("mic", 0.1)) == 1600  # ring still written
