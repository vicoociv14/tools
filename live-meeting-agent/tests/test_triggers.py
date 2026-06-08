import time
from triggers import IntervalTimer


def test_interval_timer_fires_repeatedly():
    fires: list[float] = []
    timer = IntervalTimer(interval_seconds=0.2, callback=lambda: fires.append(time.time()))
    timer.start()
    time.sleep(0.7)
    timer.stop()
    assert len(fires) >= 3
