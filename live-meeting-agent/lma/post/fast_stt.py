"""Azure Speech fast transcription (batch REST) for a finished stereo recording.

The recording is L=mic (the user), R=system (everyone else). Each channel is
extracted to mono FLAC and transcribed separately:
  mic    -> no diarization -> every phrase is "You"
  system -> diarization    -> "Speaker 1..N" (or "Remote" if diarization is off
            or unavailable, e.g. recordings >= 2 h where Azure disallows it)

Because the whole file is transcribed in one batch pass on a single timeline,
phrase ordering, sentence segmentation, and punctuation are strictly better than
the old real-time pipeline. ~60x realtime (24 min audio -> ~25 s). Locales are
identified per phrase (DE/EN). A silent channel returns HTTP 422
"NoLanguageIdentified", which is treated as "no speech".
"""
from __future__ import annotations

import io
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

API_PATH = "/speechtotext/transcriptions:transcribe?api-version=2024-11-15"
DIARIZATION_MAX_SECONDS = 2 * 3600  # Azure: diarization needs files < 2 h


def extract_channel_flac(flac_path: Path, channel: int) -> tuple[bytes, float]:
    """Return (mono FLAC bytes, duration_s) for one channel of a stereo file."""
    import soundfile as sf
    data, sr = sf.read(str(flac_path), dtype="float32")
    mono = data[:, channel] if data.ndim == 2 else data
    buf = io.BytesIO()
    sf.write(buf, mono, sr, format="FLAC", subtype="PCM_16")
    return buf.getvalue(), len(mono) / sr


def fast_transcribe(
    audio: bytes,
    *,
    endpoint: str,
    key: str,
    locales: list,
    diarize: bool,
    max_speakers: int = 6,
    timeout_s: int = 1800,
) -> list:
    """Run one fast-transcription request; return the raw `phrases` list."""
    import requests

    definition: dict = {"profanityFilterMode": "None"}
    if locales:
        definition["locales"] = list(locales)
    if diarize:
        definition["diarization"] = {"maxSpeakers": int(max_speakers), "enabled": True}

    r = requests.post(
        endpoint.rstrip("/") + API_PATH,
        headers={"Ocp-Apim-Subscription-Key": key},
        files={
            "audio": ("audio.flac", audio, "audio/flac"),
            "definition": (None, json.dumps(definition), "application/json"),
        },
        timeout=timeout_s,
    )
    if r.status_code == 422 and "NoLanguageIdentified" in r.text:
        return []  # silent channel - no speech to transcribe
    r.raise_for_status()
    return r.json().get("phrases", [])


def phrases_to_segments(phrases: list, *, speaker: str, channel: str) -> list:
    """Map raw API phrases to transcript segment dicts with a fixed speaker."""
    out = []
    for p in phrases:
        text = (p.get("text") or "").strip()
        if not text:
            continue
        start = p.get("offsetMilliseconds", 0) / 1000.0
        end = start + p.get("durationMilliseconds", 0) / 1000.0
        out.append({"start": round(start, 2), "end": round(end, 2),
                    "text": text, "speaker": speaker, "channel": channel})
    return out


def diarized_to_segments(phrases: list, *, channel: str) -> list:
    """Map diarized phrases to segments, normalizing Azure speaker ids (arbitrary
    ints) to stable 'Speaker 1..N' labels in order of first appearance."""
    label_for: dict = {}
    out = []
    for p in phrases:
        text = (p.get("text") or "").strip()
        if not text:
            continue
        sid = p.get("speaker")
        if sid is None:
            label = "Remote"
        else:
            if sid not in label_for:
                label_for[sid] = f"Speaker {len(label_for) + 1}"
            label = label_for[sid]
        start = p.get("offsetMilliseconds", 0) / 1000.0
        end = start + p.get("durationMilliseconds", 0) / 1000.0
        out.append({"start": round(start, 2), "end": round(end, 2),
                    "text": text, "speaker": label, "channel": channel})
    return out


def transcribe_recording(flac_path, config: dict, *, key: str) -> list:
    """Transcribe a stereo meeting FLAC into ordered transcript segment dicts."""
    flac_path = Path(flac_path)
    endpoint = config.get("speech_stt_endpoint", "")
    locales = config.get("speech_languages", ["de-DE", "en-US"])
    max_speakers = int(config.get("speech_max_speakers", 6))
    want_diarize = bool(config.get("speech_diarize", True))

    mic_audio, duration = extract_channel_flac(flac_path, 0)
    sys_audio, _ = extract_channel_flac(flac_path, 1)

    diarize = want_diarize and duration < DIARIZATION_MAX_SECONDS
    if want_diarize and not diarize:
        log.warning("recording %.0f s >= 2 h: Azure disallows diarization, using 'Remote'", duration)

    mic_phrases = fast_transcribe(mic_audio, endpoint=endpoint, key=key,
                                  locales=locales, diarize=False)
    sys_phrases = fast_transcribe(sys_audio, endpoint=endpoint, key=key,
                                  locales=locales, diarize=diarize,
                                  max_speakers=max_speakers)

    segments = phrases_to_segments(mic_phrases, speaker="You", channel="mic")
    if diarize:
        segments += diarized_to_segments(sys_phrases, channel="system")
    else:
        segments += phrases_to_segments(sys_phrases, speaker="Remote", channel="system")

    segments.sort(key=lambda s: s["start"])
    return segments
