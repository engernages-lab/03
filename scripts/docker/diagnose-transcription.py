#!/usr/bin/env python3
"""Diagnose a fast-failing transcription step against the running container.

Prints compact probe results (health / anonymous / authenticated / upload HTTP
codes) so a one-line summary can be put into a public artifact name. Never
replaces the real verification: it only explains a failure.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = "http://127.0.0.1:8000"
AUDIO = Path("tests/fixtures/melody.wav")


def call(method: str, path: str, token: str, data: bytes | None = None,
         extra: dict | None = None) -> tuple[int, bytes]:
    headers = dict(extra or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read()[:300]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:300]
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}".encode()


def main() -> int:
    token = sys.argv[1] if len(sys.argv) > 1 else ""
    health, _ = call("GET", "/health", "")
    anonymous, _ = call("GET", "/api/v1/audio/assets", "")
    authenticated, _ = call("GET", "/api/v1/audio/assets", token)

    upload_code = 0
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

    summary = (
        f"health={health} anon={anonymous} authed={authenticated} upload={upload_code}"
    )
    print(summary)
    print("upload_body:", upload_body.decode("utf-8", "replace")[:220])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
