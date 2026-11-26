#!/usr/bin/env python3
"""Real transcription check against a running PocketScore API (CI gate).

Talks to the real HTTP API of the container: upload a repository fixture,
create a job, run it, then validate the produced score events. Nothing is
mocked and no expected note count is hard-coded - only "there must be real,
well formed notes".

Usage:
  python3 verify-transcription.py --base-url http://127.0.0.1:8000 \
      --audio tests/fixtures/melody.wav --out docker-verification/transcription-result.json
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path


TOKEN = os.environ.get("POCKETSCORE_ACCESS_GATE_TOKEN") or os.environ.get("TEST_ACCESS_TOKEN") or ""


def request(url: str, *, method: str = "GET", data: bytes | None = None, headers: dict | None = None):
    # The staging container runs behind the access gate; the token comes from
    # --token or the environment so it never appears in a log line.
    token = TOKEN
    merged = dict(headers or {})
    if token:
        merged.setdefault("Authorization", f"Bearer {token}")
    req = urllib.request.Request(url, data=data, method=method, headers=merged)
    with urllib.request.urlopen(req, timeout=120) as response:
        body = response.read()
        return response.status, (json.loads(body) if body else None)


def upload(base: str, audio: Path) -> dict:
    boundary = f"----pocketscore{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(audio.name)[0] or "application/octet-stream"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{audio.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    body = head + audio.read_bytes() + tail
    status, payload = request(
        f"{base}/api/v1/audio/upload",
        method="POST",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    if status >= 300 or not payload:
        raise SystemExit(f"upload failed: HTTP {status} {payload}")
    return payload


def audio_metadata(audio: Path) -> dict:
    info = {"bytes": audio.stat().st_size, "suffix": audio.suffix.lower()}
    try:
        with wave.open(str(audio), "rb") as handle:
            info["duration_seconds"] = round(handle.getnframes() / float(handle.getframerate()), 3)
            info["sample_rate"] = handle.getframerate()
            info["channels"] = handle.getnchannels()
    except Exception:
        info["duration_seconds"] = None
    return info


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--audio", default="tests/fixtures/melody.wav")
    parser.add_argument("--out", default="docker-verification/transcription-result.json")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--token", default="", help="access gate bearer token")
    args = parser.parse_args()

    global TOKEN
    if args.token:
        TOKEN = args.token

    base = args.base_url.rstrip("/")
    audio = Path(args.audio)
    if not audio.is_file():
        print(f"::error::audio fixture missing: {audio}")
        return 1

    result: dict = {"base_url": base, "audio": audio_metadata(audio), "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    started = time.perf_counter()
    asset = upload(base, audio)
    result["upload_seconds"] = round(time.perf_counter() - started, 3)
    result["asset_id"] = asset.get("asset_id")
    result["asset_duration"] = asset.get("duration")
    result["asset_size_bytes"] = asset.get("size_bytes")
    result["asset_checksum"] = asset.get("checksum_sha256")

    body = json.dumps({"asset_id": result["asset_id"]}).encode()
    status, job = request(
        f"{base}/api/v1/transcription/jobs",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    if status >= 300 or not job:
        print(f"::error::job creation failed: HTTP {status} {job}")
        return 1
    result["job_id"] = job["job_id"]

    started = time.perf_counter()
    status, done = request(f"{base}/api/v1/transcription/jobs/{result['job_id']}/run", method="POST")
    result["job_seconds"] = round(time.perf_counter() - started, 3)
    result["job_http"] = status

    # 503 INFERENCE_BUSY is a capacity signal, not a correctness failure: retry a
    # few times the way a real client would instead of lowering the bar.
    attempt = 0
    while status == 503 and attempt < 3:
        attempt += 1
        time.sleep(5 * attempt)
        started = time.perf_counter()
        status, done = request(f"{base}/api/v1/transcription/jobs/{result['job_id']}/run", method="POST")
        result["job_seconds"] = round(time.perf_counter() - started, 3)
        result["job_http"] = status
        result["retries"] = attempt

    if status >= 300 or not done:
        print(f"::error::transcription failed: HTTP {status} {done}")
        result["state"] = "http_error"
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
        return 1

    result["state"] = done.get("status")
    result["events_reported"] = done.get("events_produced")
    result["analysis"] = {
        key: (done.get("analysis") or {}).get(key)
        for key in ("model_load_seconds", "inference_seconds", "queue_wait_seconds")
    }
    result["pipeline"] = done.get("pipeline")

    document_id = done.get("document_id")
    result["document_id"] = document_id
    if not document_id:
        print("::error::job completed without a document")
        return 1

    status, document = request(f"{base}/api/v1/documents/{document_id}")
    if status >= 300 or not document:
        print(f"::error::document read failed: HTTP {status}")
        return 1

    events = document.get("events") or []
    result["document_events"] = len(events)
    result["document_title"] = document.get("title")

    # --- validate the notes themselves ------------------------------------
    pitches: list[int] = []
    problems: list[str] = []
    for index, event in enumerate(events):
        pitch = event.get("pitch")
        start = event.get("start_time")
        duration = event.get("duration")
        if not isinstance(pitch, int) or not (0 <= pitch <= 127):
            problems.append(f"event {index}: pitch {pitch!r} outside 0-127")
            continue
        pitches.append(pitch)
        if not isinstance(start, (int, float)) or start < 0:
            problems.append(f"event {index}: start_time {start!r} invalid")
        if not isinstance(duration, (int, float)) or duration <= 0:
            problems.append(f"event {index}: duration {duration!r} invalid")

    result["distinct_pitches"] = sorted(set(pitches))
    result["problems"] = problems

    status, both = request(f"{base}/api/v1/notation/{document_id}/both")
    result["notation_http"] = status
    if status == 200 and both:
        result["grid_notes"] = both.get("grid", {}).get("stats", {}).get("notes")
        result["jianpu_notes"] = both.get("jianpu", {}).get("stats", {}).get("notes")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")

    failures = []
    if result["state"] != "completed":
        failures.append(f"job state {result['state']!r}")
    if (result["events_reported"] or 0) <= 0:
        failures.append("events_produced is 0 (no transcription)")
    if result["document_events"] <= 0:
        failures.append("document has no note events")
    if problems:
        failures.extend(problems[:5])
    if result.get("grid_notes") in (0, None):
        failures.append("grid notation reports no notes")
    if result.get("jianpu_notes") in (0, None):
        failures.append("jianpu notation reports no notes")

    if failures:
        print("TRANSCRIPTION VERIFY FAILED")
        for item in failures:
            print(" -", item)
        return 1

    print(
        "TRANSCRIPTION VERIFY OK:",
        result["document_events"], "notes, pitches", result["distinct_pitches"],
        "in", result["job_seconds"], "s (model load", result["analysis"]["model_load_seconds"], "s)",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
