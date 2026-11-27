#!/usr/bin/env python3
"""V1.1-C.2.2.2 Phase 11: compare before/after restart snapshots field by field.

Fails loudly on any difference that matters. HTTP 200 alone is never treated as
proof of persistence.

Usage:
  python scripts/deploy/compare-staging-persistence.py \
    --before artifacts/before-restart.json --after artifacts/after-restart.json \
    --out artifacts/persistence-diff.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FIELDS = [
    ("project.document_id", "Project ID"),
    ("project.title", "Project Name"),
    ("project.asset_id", "Audio Asset ID"),
    ("notes.count", "Note Count"),
    ("notes.pitch_sequence", "Pitch Sequence"),
    ("notes.onset_sequence", "Onset Sequence"),
    ("notes.duration_sequence", "Duration Sequence"),
    ("notes.velocity_sequence", "Velocity Sequence"),
    ("audio.sha256", "Audio SHA256"),
    ("audio.size_bytes", "Audio File Size"),
    ("notation.grid", "Grid Stats"),
    ("notation.jianpu", "Jianpu Stats"),
]


def dig(data: dict, dotted: str):
    value = data
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))

    rows = []
    problems = []
    for dotted, label in FIELDS:
        old = dig(before, dotted)
        new = dig(after, dotted)
        same = old == new
        rows.append({"field": label, "before": old, "after": new, "identical": same})
        if not same:
            problems.append(f"{label}: {old!r} -> {new!r}")

    ready_ok = (after.get("ready") or {}).get("ready") is True
    health_ok = (after.get("health") or {}).get("http") == 200
    if not ready_ok:
        problems.append("service is not ready after the restart")
    if not health_ok:
        problems.append("health probe failed after the restart")

    result = {
        "before_captured_at": before.get("captured_at"),
        "after_captured_at": after.get("captured_at"),
        "rows": rows,
        "health_after": health_ok,
        "ready_after": ready_ok,
        "identical": not problems,
        "problems": problems,
    }
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")

    width = max(len(row["field"]) for row in rows)
    print(f"{'field'.ljust(width)}  before -> after   identical")
    for row in rows:
        print(f"{row['field'].ljust(width)}  {'yes' if row['identical'] else 'NO'}")

    if problems:
        print("\nPERSISTENCE FAILED")
        for problem in problems:
            print(" -", problem)
        return 1

    print("\nPERSISTENCE OK: every compared field survived the restart unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
