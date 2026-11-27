#!/usr/bin/env python3
"""V1.1-C.2.2.2 Phase 9/11: snapshot a project's full state from staging.

Captures everything needed to prove persistence: document metadata, the complete
note list, both notation views, and the audio bytes (hashed, never stored in the
report). Run once before the restart and once after, then compare with
compare-staging-persistence.py.

Usage:
  PSC_STAGING_URL=... POCKETSCORE_ACCESS_GATE_TOKEN=... \
    python scripts/deploy/verify-staging-persistence.py --document-id XYZ --out before-restart.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ARTIFACTS = Path("reports/V1.1-C.2.2.2/artifacts")
BASE = os.environ.get("PSC_STAGING_URL", "").rstrip("/")
TOKEN = os.environ.get("POCKETSCORE_ACCESS_GATE_TOKEN", "")


def raw(path: str, timeout: int = 120) -> tuple[int, bytes]:
    request = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def call(path: str, timeout: int = 120):
    status, body = raw(path, timeout=timeout)
    try:
        return status, json.loads(body) if body else None
    except json.JSONDecodeError:
        return status, body[:300].decode("utf-8", "replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--out", required=True, help="file name under artifacts/")
    args = parser.parse_args()

    if not BASE or not TOKEN:
        print("PSC_STAGING_URL and POCKETSCORE_ACCESS_GATE_TOKEN are required")
        return 2

    doc_id = args.document_id
    status, document = call(f"/api/v1/documents/{doc_id}")
    if status != 200 or not isinstance(document, dict):
        print("document unreadable:", status, document)
        return 1

    events = document.get("events") or []
    # The audio reference lives in source_metadata; document.asset_id is not used.
    source_metadata = document.get("source_metadata") or {}
    asset_id = source_metadata.get("source_audio_asset_id")
    recognition = {
        "kind": source_metadata.get("kind"),
        "filename": source_metadata.get("filename"),
        "provider": source_metadata.get("provider"),
        "recognition_model": source_metadata.get("recognition_model"),
        "recognition_version": source_metadata.get("recognition_version"),
    }
    status_notation, notation = call(f"/api/v1/notation/{doc_id}/both")
    status_health, health = call("/health")
    status_ready, ready = call("/ready")

    audio_sha = None
    audio_size = None
    audio_http = None
    if asset_id:
        audio_http, audio_bytes = raw(f"/api/v1/audio/assets/{asset_id}/stream")
        if audio_http == 200:
            audio_sha = hashlib.sha256(audio_bytes).hexdigest()
            audio_size = len(audio_bytes)

    snapshot = {
        "label": Path(args.out).stem,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "project": {
            "document_id": doc_id,
            "title": document.get("title"),
            "artist": document.get("artist"),
            "version": document.get("schema_version") or document.get("version"),
            "asset_id": asset_id,
            "track_count": len(document.get("tracks") or []),
        },
        "notes": {
            "count": len(events),
            "pitch_sequence": [event.get("pitch") for event in events],
            "onset_sequence": [round(event.get("start_time"), 4) for event in events],
            "duration_sequence": [round(event.get("duration"), 4) for event in events],
            "velocity_sequence": [event.get("velocity") for event in events],
        },
        "notation": {
            "http": status_notation,
            "grid": (notation or {}).get("grid", {}).get("stats"),
            "jianpu": (notation or {}).get("jianpu", {}).get("stats"),
            "same_document": (notation or {}).get("grid", {}).get("document_id")
            == (notation or {}).get("jianpu", {}).get("document_id")
            == doc_id,
        },
        "audio": {"http": audio_http, "sha256": audio_sha, "size_bytes": audio_size, "asset_id": asset_id},
        "recognition": recognition,
        "health": {"http": status_health, "body": health},
        "ready": {
            "http": status_ready,
            "ready": (ready or {}).get("ready"),
            "checks": sorted(((ready or {}).get("checks") or {}).keys()),
        },
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    target = ARTIFACTS / args.out
    target.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(json.dumps(snapshot["project"], indent=2))
    print(
        "notes:",
        snapshot["notes"]["count"],
        "| pitches:",
        snapshot["notes"]["pitch_sequence"],
        "| audio:",
        snapshot["audio"]["size_bytes"],
        snapshot["audio"]["sha256"],
    )
    print("wrote", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
