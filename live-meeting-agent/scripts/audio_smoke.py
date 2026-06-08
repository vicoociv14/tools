import time
import sys
from pathlib import Path

# allow running from project root or from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio import RingBuffer, CaptureThread

ring = RingBuffer(capacity_seconds=10)
cap = CaptureThread(ring)
cap.start()
print("capturing for 5 seconds, play some audio (YouTube, Spotify, etc.)...")
time.sleep(5)
cap.stop()
samples = ring.read_since(5)
print(f"captured {len(samples)} samples, max amplitude {abs(samples).max():.3f}")
print("If max amplitude is 0.000, no audio was captured. Check your default audio output.")
