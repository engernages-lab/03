#!/usr/bin/env python3
"""V1.1-C.2.2.2 Phase 6/7: real WAV/MP3 transcription against Railway staging.

Uploads a real audio file over HTTPS, runs the real Basic Pitch pipeline, then
validates the resulting MusicDocument note by note. No mocks, no pre-seeded
notes: every number in the evidence file comes from the running service.

Usage:
  PSC_STAGING_URL=https://... POCKETSCORE_ACCESS_GATE_TOKEN=... \
    python scripts/deploy/verify-staging-audio.py --audio .run/audio/melody.mp3 --label mp3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

ARTIFACTS = Path("reports/V1.1-C.2.2.2/artifacts")
TOKEN = os.environ.get("POCKETSCORE_ACCESS_GATE_TOKEN", "")
BASE = os.environ.get("PSC_STAGING_URL", "").rstrip("/")


def call(path: str, *, method: str = "GET", data: bytes | None = None, headers: dict | None = None, timeout: int = 180):
    merged = dict(headers or {})
    if TOKEN:
        merged.setdefault("Authorization", f"Bearer {TOKEN}")
    request = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=merged)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return response.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            payload = json.loads(body) if body else None
        except json.JSONDecodeError:
            payload = body[:500].decode("utf-8", "replace")
        return exc.code, payload


def upload(audio: Path) -> tuple[int, dict]:
    boundary = f"----pocketscore{uuid.uuid4().hex}"
    mime = "audio/mpeg" if audio.suffix.lower() == ".mp3" else "audio/wav"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{audio.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    body = head + audio.read_bytes() + tail
    status, payload = call(
        "/api/v1/audio/upload",
        method="POST",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    return status, payload


def wav_info(audio: Path) -> dict:
    if audio.suffix.lower() != ".wav":
        return {}
    with wave.open(str(audio), "rb") as handle:
        return {
            "sample_rate": handle.getframerate(),
            "channels": handle.getnchannels(),
            "frames": handle.getnframes(),
            "duration_seconds": round(handle.getnframes() / float(handle.getframerate()), 3),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--label", required=True, help="wav or mp3 (evidence file prefix)")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    if not BASE or not TOKEN:
        print("PSC_STAGING_URL and POCKETSCORE_ACCESS_GATE_TOKEN are required")
        return 2

    audio = Path(args.audio)
    if not audio.is_file():
        print("missing audio:", audio)
        return 2

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    payload_bytes = audio.read_bytes()
    result: dict = {
        "label": args.label,
        "base_url": BASE,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "file": {
            "name": audio.name,
            "suffix": audio.suffix.lower(),
            "size_bytes": len(payload_bytes),
            "sha256": hashlib.sha256(payload_bytes).hexdigest(),
        },
    }
    result["file"].update(wav_info(audio))

    started = time.perf_counter()
    status, asset = upload(audio)
    result["upload"] = {
        "http": status,
        "seconds": round(time.perf_counter() - started, 3),
        "asset_id": (asset or {}).get("asset_id"),
        "reported_duration": (asset or {}).get("duration"),
        "reported_size": (asset or {}).get("size_bytes"),
        "reported_checksum": (asset or {}).get("checksum_sha256"),
    }
    (ARTIFACTS / f"{args.label}-upload-response.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    if status != 201 or not result["upload"]["asset_id"]:
        print("UPLOAD FAILED", status, json.dumps(asset)[:400] if asset else "")
        return 1

    body = json.dumps({"asset_id": result["upload"]["asset_id"]}).encode()
    status, job = call("/api/v1/transcription/jobs", method="POST", data=body, headers={"Content-Type": "application/json"})
    if status >= 300 or not job:
        print("JOB CREATE FAILED", status, job)
        return 1
    job_id = job["job_id"]

    started = time.perf_counter()
    status, done = call(f"/api/v1/transcription/jobs/{job_id}/run", method="POST")
    attempts = 1
    while status == 503 and attempts < 4:
        time.sleep(5 * attempts)
        started = time.perf_counter()
        status, done = call(f"/api/v1/transcription/jobs/{job_id}/run", method="POST")
        attempts += 1

    result["job"] = {
        "job_id": job_id,
        "http": status,
        "seconds": round(time.perf_counter() - started, 3),
        "attempts": attempts,
        "state": (done or {}).get("status"),
        "events_produced": (done or {}).get("events_produced"),
        "analysis": (done or {}).get("analysis"),
        "pipeline": (done or {}).get("pipeline"),
        "document_id": (done or {}).get("document_id"),
        "error": (done or {}).get("error"),
    }
    if status >= 300 or not result["job"]["document_id"]:
        (ARTIFACTS / f"{args.label}-transcription-result.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print("TRANSCRIBE FAILED", status, json.dumps(done)[:600] if done else "")
        return 1

    status, document = call(f"/api/v1/documents/{result['job']['document_id']}")
    events = (document or {}).get("events") or []
    pitches = [e.get("pitch") for e in events]
    onsets = [e.get("start_time") for e in events]
    durations = [e.get("duration") for e in events]

    status_n, notation = call(f"/api/v1/notation/{result['job']['document_id']}/both")
    result["document"] = {
        "http": status,
        "document_id": result["job"]["document_id"],
        "title": (document or {}).get("title"),
        "note_count": len(events),
        "pitch_sequence": pitches,
        "onset_sequence": [round(v, 4) if isinstance(v, (int, float)) else v for v in onsets],
        "duration_sequence": [round(v, 4) if isinstance(v, (int, float)) else v for v in durations],
        "unique_pitch_count": len(set(pitches)),
        "pitch_min": min(pitches) if pitches else None,
        "pitch_max": max(pitches) if pitches else None,
    }
    result["notation"] = {
        "http": status_n,
        "grid_notes": ((notation or {}).get("grid") or {}).get("stats", {}).get("notes"),
        "jianpu_notes": ((notation or {}).get("jianpu") or {}).get("stats", {}).get("notes"),
        "same_document": (notation or {}).get("grid", {}).get("document_id")
        == (notation or {}).get("jianpu", {}).get("document_id"),
    }
    (ARTIFACTS / f"{args.label}-transcription-result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )

    problems: list[str] = []
    if result["job"]["state"] != "completed":
        problems.append(f"job state {result['job']['state']!r}")
    if not events:
        problems.append("no note events")
    if any(not isinstance(p, int) or not 0 <= p <= 127 for p in pitches):
        problems.append("pitch outside 0-127")
    if any(not isinstance(o, (int, float)) or o < 0 for o in onsets):
        problems.append("invalid onset")
    if any(not isinstance(d, (int, float)) or d <= 0 for d in durations):
        problems.append("invalid duration")
    if any(isinstance(v, float) and (math.isnan(v) or math.isinf(v)) for v in onsets + durations):
        problems.append("NaN/Inf in timing")
    if len(set(onsets)) < 2:
        problems.append("all onsets identical")
    if result["notation"]["grid_notes"] in (0, None):
        problems.append("grid notation has no notes")
    if result["notation"]["jianpu_notes"] in (0, None):
        problems.append("jianpu notation has no notes")

    print(
        f"{args.label.upper()} OK: {len(events)} notes, pitches {sorted(set(pitches))}, "
        f"job {result['job']['seconds']}s, upload {result['upload']['seconds']}s"
    )
    if problems:
        print("PROBLEMS:", problems)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
