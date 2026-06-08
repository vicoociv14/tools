import asyncio
import threading

from lma.server.hub import TranscriptHub
from lma.brain.state import Segment


def _seg(t):
    return Segment(start=t, end=t + 1, text=f"s{t}", speaker="You", channel="mic")


def test_fanout_delivers_to_all_subscribers():
    hub = TranscriptHub()
    q1, q2 = hub.add_subscriber(), hub.add_subscriber()
    hub._fanout(_seg(1))
    assert q1.get_nowait().text == "s1"
    assert q2.get_nowait().text == "s1"


def test_unsubscribe_stops_delivery():
    hub = TranscriptHub()
    q = hub.add_subscriber()
    hub.remove_subscriber(q)
    hub._fanout(_seg(1))
    assert q.empty()


def test_publish_without_loop_is_noop():
    hub = TranscriptHub()
    hub.publish(_seg(1))  # no loop bound -> must not raise


def test_publish_threadsafe_reaches_subscriber():
    async def run():
        hub = TranscriptHub()
        hub.bind_loop(asyncio.get_running_loop())
        q = hub.add_subscriber()
        threading.Thread(target=lambda: hub.publish(_seg(7))).start()
        for _ in range(50):
            try:
                return q.get_nowait()
            except Exception:
                await asyncio.sleep(0.02)
        return None

    seg = asyncio.run(run())
    assert seg is not None and seg.text == "s7"
