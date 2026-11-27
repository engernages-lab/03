#!/usr/bin/env python3
"""V1.1-C.2.2.2 Phase 8: MusicDocument / project save + read against staging.

Creates an independent document from the real MP3 transcription result, renames
it with a unique regression marker, writes an edit through the public API, then
reads everything back and compares grid vs jianpu against the same document.
"""

from __future__ import annotations

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


def call(path: str, *, method: str = "GET", payload: dict | None = None, timeout: int = 120):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return response.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            return exc.code, json.loads(body) if body else None
        except json.JSONDecodeError:
            return exc.code, body[:300].decode("utf-8", "replace")


def main() -> int:
    if not BASE or not TOKEN:
        print("PSC_STAGING_URL and POCKETSCORE_ACCESS_GATE_TOKEN are required")
        return 2

    source = json.loads((ARTIFACTS / "mp3-transcription-result.json").read_text(encoding="utf-8"))
    document_id = source["document"]["document_id"]
    marker = "C2-2-2-STAGING-REGRESSION-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

    result: dict = {"marker": marker, "source_document_id": document_id}

    # 1. read the document produced by the real MP3 transcription
    status, document = call(f"/api/v1/documents/{document_id}")
    result["read"] = {
        "http": status,
        "title": (document or {}).get("title"),
        "note_count": len((document or {}).get("events") or []),
        "asset_id": (document or {}).get("asset_id"),
    }

    # 2. name the project uniquely (a real write, not a read-only claim)
    status_patch, patched = call(
        f"/api/v1/documents/{document_id}", method="PATCH", payload={"title": marker}
    )
    result["rename"] = {"http": status_patch, "title": (patched or {}).get("title")}

    # 3. edit through the public API: transpose +1 semitone, verify BOTH notation
    #    views follow the same document, then transpose back so the persisted
    #    state stays comparable with the pre-restart snapshot.
    events = (document or {}).get("events") or []
    pitches_before = sorted({event.get("pitch") for event in events})
    edit: dict = {"http": None}
    if events:
        status_up, up = call(
            f"/api/v1/documents/{document_id}/edits",
            method="POST",
            payload={"operations": [{"op": "transpose", "semitones": 1}]},
        )
        _, after_up = call(f"/api/v1/documents/{document_id}")
        pitches_up = sorted({event.get("pitch") for event in ((after_up or {}).get("events") or [])})
        _, notation_up = call(f"/api/v1/notation/{document_id}/both")
        grid_up = ((notation_up or {}).get("grid") or {})
        jianpu_up = ((notation_up or {}).get("jianpu") or {})

        status_down, _ = call(
            f"/api/v1/documents/{document_id}/edits",
            method="POST",
            payload={"operations": [{"op": "transpose", "semitones": -1}]},
        )
        _, after_down = call(f"/api/v1/documents/{document_id}")
        pitches_down = sorted({event.get("pitch") for event in ((after_down or {}).get("events") or [])})

        edit = {
            "http": status_up,
            "revert_http": status_down,
            "pitches_before": pitches_before,
            "pitches_after_transpose_up": pitches_up,
            "pitches_after_revert": pitches_down,
            "transpose_applied": pitches_up == [p + 1 for p in pitches_before],
            "revert_restored": pitches_down == pitches_before,
            "grid_notes_after_edit": (grid_up.get("stats") or {}).get("notes"),
            "jianpu_notes_after_edit": (jianpu_up.get("stats") or {}).get("notes"),
            "notation_still_same_document": grid_up.get("document_id")
            == jianpu_up.get("document_id")
            == document_id,
        }
    result["edit"] = edit

    # 4. read again: the write must be visible, from storage not from memory
    status_again, again = call(f"/api/v1/documents/{document_id}")
    result["reread"] = {
        "http": status_again,
        "title": (again or {}).get("title"),
        "note_count": len((again or {}).get("events") or []),
    }

    # 5. grid and jianpu must describe the same document
    status_notation, both = call(f"/api/v1/notation/{document_id}/both")
    grid = (both or {}).get("grid") or {}
    jianpu = (both or {}).get("jianpu") or {}
    result["notation"] = {
        "http": status_notation,
        "grid_notes": (grid.get("stats") or {}).get("notes"),
        "grid_unmapped": (grid.get("stats") or {}).get("unmapped"),
        "jianpu_notes": (jianpu.get("stats") or {}).get("notes"),
        "jianpu_unmapped": (jianpu.get("stats") or {}).get("unmapped"),
        "grid_document_id": grid.get("document_id"),
        "jianpu_document_id": jianpu.get("document_id"),
        "same_document": grid.get("document_id") == jianpu.get("document_id") == document_id,
    }
    result["list"] = {}
    status_list, listing = call("/api/v1/documents?limit=50")
    items = (listing or {}).get("items") or []
    result["list"] = {
        "http": status_list,
        "total": (listing or {}).get("total"),
        "contains_document": any(item.get("document_id") == document_id for item in items),
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "project-document-check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

    problems = []
    if result["read"]["http"] != 200 or result["read"]["note_count"] <= 0:
        problems.append("document unreadable or empty")
    if result["rename"]["http"] not in (200, 201) or result["rename"]["title"] != marker:
        problems.append("rename did not persist")
    if result["reread"]["title"] != marker:
        problems.append("re-read lost the rename")
    if not result["notation"]["same_document"]:
        problems.append("grid/jianpu not from the same document")
    # The two views count differently and the contract must respect that:
    #   grid   : notes = rendered, unmapped = dropped from the grid  -> notes+unmapped == total
    #   jianpu : notes = all notes, unmapped = subset lacking a keyboard row
    # Anything else means notes were lost.
    total = result["read"]["note_count"]
    grid_mapped = result["notation"].get("grid_notes") or 0
    grid_unmapped = result["notation"].get("grid_unmapped") or 0
    jianpu_notes = result["notation"].get("jianpu_notes") or 0
    jianpu_unmapped = result["notation"].get("jianpu_unmapped") or 0
    if grid_mapped <= 0:
        problems.append("grid view has no rendered notes")
    if grid_mapped + grid_unmapped != total:
        problems.append(f"grid lost notes: {grid_mapped}+{grid_unmapped} != {total}")
    if jianpu_notes != total:
        problems.append(f"jianpu lost notes: {jianpu_notes} != {total}")
    if jianpu_unmapped > jianpu_notes:
        problems.append(f"jianpu unmapped {jianpu_unmapped} exceeds notes {jianpu_notes}")
    if not result["list"]["contains_document"]:
        problems.append("document missing from the list endpoint")

    if problems:
        print("PROBLEMS:", problems)
        return 1
    print("DOCUMENT/PROJECT OK: renamed, re-read, both notation views consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
