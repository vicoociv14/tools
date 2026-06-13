"""Probe Azure Speech fast transcription (batch REST) with a real recording.

Splits the stereo FLAC into mono channels and sends:
  - mic channel  (no diarization)            -> expect all phrases, speaker=You
  - system channel (diarization, maxSpeakers) -> expect speaker ids per phrase

Verifies endpoint, auth, response shape, ordering, and locale detection.

  set LMA_FOUNDRY_API_KEY=...
  python scripts/fast_stt_probe.py recordings/2026-06/<file>.flac
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

KEY = os.environ.get("LMA_SPEECH_KEY") or os.environ["LMA_FOUNDRY_API_KEY"]
ENDPOINTS = [
    "https://vstr-mq4q2wgo-swedencentral.cognitiveservices.azure.com",
    "https://vstr-mq4q2wgo-swedencentral.services.ai.azure.com",
    "https://swedencentral.api.cognitive.microsoft.com",
]
API = "/speechtotext/transcriptions:transcribe?api-version=2024-11-15"

src = Path(sys.argv[1])
data, sr = sf.read(str(src), dtype="float32")
print(f"src={src.name} sr={sr} shape={data.shape} dur={len(data)/sr:.0f}s")


def mono_flac_bytes(channel: int) -> bytes:
    buf = io.BytesIO()
    mono = data[:, channel] if data.ndim == 2 else data
    sf.write(buf, mono, sr, format="FLAC", subtype="PCM_16")
    return buf.getvalue()


def transcribe(endpoint: str, audio: bytes, label: str, diarize: bool):
    definition = {
        "locales": ["de-DE", "en-US"],
        "profanityFilterMode": "None",
    }
    if diarize:
        definition["diarization"] = {"maxSpeakers": 6, "enabled": True}
    t0 = time.time()
    r = requests.post(
        endpoint + API,
        headers={"Ocp-Apim-Subscription-Key": KEY},
        files={
            "audio": (f"{label}.flac", audio, "audio/flac"),
            "definition": (None, json.dumps(definition), "application/json"),
        },
        timeout=600,
    )
    print(f"[{label}] {endpoint} -> HTTP {r.status_code} in {time.time()-t0:.1f}s")
    if r.status_code != 200:
        print(r.text[:500])
        return None
    return r.json()


# Find a working endpoint with the mic channel first
mic_audio = mono_flac_bytes(0)
result = None
endpoint_ok = None
for ep in ENDPOINTS:
    result = transcribe(ep, mic_audio, "mic", diarize=False)
    if result is not None:
        endpoint_ok = ep
        break

if result is None:
    sys.exit("no endpoint worked")

print(f"\nWORKING ENDPOINT: {endpoint_ok}")
phrases = result.get("phrases", [])
print(f"mic phrases: {len(phrases)}")
for p in phrases[:6]:
    print(f"  [{p['offsetMilliseconds']/1000:7.1f}s {p.get('locale','?')}] {p['text'][:80]}")

sys_audio = mono_flac_bytes(1)
res2 = transcribe(endpoint_ok, sys_audio, "system", diarize=True)
if res2:
    phrases2 = res2.get("phrases", [])
    print(f"system phrases: {len(phrases2)}")
    speakers = sorted({p.get("speaker") for p in phrases2})
    print(f"distinct speakers: {speakers}")
    for p in phrases2[:8]:
        print(f"  [{p['offsetMilliseconds']/1000:7.1f}s spk={p.get('speaker')} {p.get('locale','?')}] {p['text'][:70]}")
