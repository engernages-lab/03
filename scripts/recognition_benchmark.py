"""Run the transcription benchmark and print real precision/recall/F1.

Usage:
    python scripts/recognition_benchmark.py --split dev
    python scripts/recognition_benchmark.py --split test --json
    python scripts/recognition_benchmark.py --split dev --min-note-ms 30 --onset 0.4

The corpus is synthesised from ``backend/tests/benchmark/corpus.py``; each case
also writes a MIDI file so the ground truth is inspectable, not just an array.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))

from benchmark import corpus, metrics  # noqa: E402

from app.services.audio import note_extraction  # noqa: E402


def run(split: str, overrides: dict) -> dict:
    directory = Path(tempfile.mkdtemp(prefix=f"pocketscore-bench-{split}-"))
    cases = corpus.build_corpus(directory, split)

    per_case = []
    scores = []
    by_category: dict[str, list] = defaultdict(list)
    for case in cases:
        detected = note_extraction.transcribe_file(Path(case["wav"]), **overrides)
        ends = [start + duration for _pitch, start, duration in case["bounds"]]
        case_score = metrics.score(
            [
                metrics.Detected(pitch=note.pitch, start=note.start, end=note.end, amplitude=note.amplitude)
                for note in detected
            ],
            case["reference"],
            duration=case["duration"],
            reference_ends=ends,
        )
        per_case.append({"case": case["name"], "category": case["category"], **case_score.as_dict()})
        scores.append(case_score)
        by_category[case["category"]].append(case_score)

    return {
        "split": split,
        "overrides": overrides,
        "cases": per_case,
        "overall": metrics.aggregate(scores).as_dict(),
        "by_category": {
            name: metrics.aggregate(items).as_dict() for name, items in sorted(by_category.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PocketScore transcription benchmark")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--min-note-ms", type=float, default=None)
    parser.add_argument("--onset", type=float, default=None)
    parser.add_argument("--frame", type=float, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    overrides = {}
    if args.min_note_ms is not None:
        overrides["minimum_note_length_ms"] = args.min_note_ms
    if args.onset is not None:
        overrides["onset_threshold"] = args.onset
    if args.frame is not None:
        overrides["frame_threshold"] = args.frame

    splits = ["dev", "test"] if args.split == "all" else [args.split]
    report = [run(split, overrides) for split in splits]

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    for section in report:
        print(f"\n=== split: {section['split']} | overrides: {section['overrides'] or 'defaults'} ===")
        header = f"{'case':24} {'cat':15} {'ref':>4} {'det':>4} {'TP':>3} {'FP':>3} {'FN':>3} {'P':>6} {'R':>6} {'F1':>6}"
        print(header)
        print("-" * len(header))
        for item in section["cases"]:
            print(
                f"{item['case']:24} {item['category']:15} {item['reference']:4d} {item['detected']:4d} "
                f"{item['tp']:3d} {item['fp']:3d} {item['fn']:3d} "
                f"{item['precision']:6.3f} {item['recall']:6.3f} {item['f1']:6.3f}"
            )
        print("-" * len(header))
        for name, cat in section["by_category"].items():
            print(
                f"{'[' + name + ']':24} {'':15} {cat['reference']:4d} {cat['detected']:4d} "
                f"{cat['tp']:3d} {cat['fp']:3d} {cat['fn']:3d} "
                f"{cat['precision']:6.3f} {cat['recall']:6.3f} {cat['f1']:6.3f}"
            )
        overall = section["overall"]
        print(
            f"{'OVERALL':24} {'':15} {overall['reference']:4d} {overall['detected']:4d} "
            f"{overall['tp']:3d} {overall['fp']:3d} {overall['fn']:3d} "
            f"{overall['precision']:6.3f} {overall['recall']:6.3f} {overall['f1']:6.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
