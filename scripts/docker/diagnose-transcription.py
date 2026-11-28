#!/usr/bin/env python3
"""Diagnose a fast-failing transcription step against the running container.

Probes the same sequence the real check uses (health, anonymous, authenticated,
upload, create job, run job) and prints compact status/error codes. The CI step
turns that line into a public artifact name, which is the only diagnostics channel
available when repository logs need credentials.

Never a substitute for the real verification: it explains a failure, it does not
pass the step.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = "http://127.0.0.1:8000"
AUDIO = Path("tests/fixtures/melody.wav")


def _error_code(body: bytes) -> str:
    try:
        payload = json.loads(body)
    except Exception:  # noqa: BLE001
        return ""
    error = payload.get("error") if isinstance(payload, dict) else None
    code = (error or {}).get("code") if isinstance(error, dict) else None
    return re.sub(r"[^A-Za-z0-9_-]", "", str(code))[:28] if code else ""


def call(method: str, path: str, token: str, data: bytes | None = None,
         extra: dict | None = None) -> tuple[int, bytes]:
    """Return (status, body); status 0 means a transport failure.

    The body carries the exception class so the CI step can publish it through a
    public artifact name -- the only diagnostics channel available here.
    """
    headers = dict(extra or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read()[:400]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:400]
    except Exception as exc:  # noqa: BLE001
        return 0, f"TRANSPORT {type(exc).__name__}: {exc}".encode()


def main() -> int:
    token = sys.argv[1] if len(sys.argv) > 1 else ""

    health, _ = call("GET", "/health", "")
    anonymous, _ = call("GET", "/api/v1/audio/assets", "")
    authenticated, _ = call("GET", "/api/v1/audio/assets", token)

    upload_code = 0
    asset_id = None
    upload_body = b""
    if AUDIO.is_file():
        boundary = "----diag" + uuid.uuid4().hex
        head = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="melody.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode()
        tail = f"\r\n--{boundary}--\r\n".encode()
        upload_code, upload_body = call(
            "POST", "/api/v1/audio/upload", token,
            head + AUDIO.read_bytes() + tail,
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            asset_id = json.loads(upload_body).get("asset_id")
        except Exception:  # noqa: BLE001
            asset_id = None

    job_code = 0
    job_error = ""
    job_id = None
    job_body = b""
    after_job = 0
    if asset_id:
        job_code, job_body = call(
            "POST", "/api/v1/transcription/jobs", token,
            json.dumps({"asset_id": asset_id}).encode(),
            {"Content-Type": "application/json"},
        )
        job_error = _error_code(job_body)
        if job_code == 0:
            job_error = "TRANSPORT"
        try:
            job_id = json.loads(job_body).get("job_id")
        except Exception:  # noqa: BLE001
            job_id = None
    after_job, _ = call("GET", "/health", "")

    run_code = 0
    run_error = ""
    state = ""
    events = ""
    if job_id:
        run_code, run_body = call("POST", f"/api/v1/transcription/jobs/{job_id}/run", token)
        run_error = _error_code(run_body)
        try:
            payload = json.loads(run_body)
            state = str(payload.get("status", ""))
            events = str(payload.get("events_produced", ""))
        except Exception:  # noqa: BLE001
            pass

    print(
        f"health={health} anon={anonymous} authed={authenticated} upload={upload_code} "
        f"job={job_code}{('-' + job_error) if job_error else ''} "
        f"after={after_job} "
        f"run={run_code}{('-' + run_error) if run_error else ''} "
        f"state={state or 'none'} events={events or 'none'}"
    )
    if job_code == 0:
        print("job_transport:", job_body.decode("utf-8", "replace")[:300])
    if not asset_id:
        print("upload_body:", upload_body.decode("utf-8", "replace")[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
