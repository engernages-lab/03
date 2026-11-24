"""Post-deployment acceptance check for PocketScore AI.

Runs the A.9.5 checklist against any reachable base URL (local production mode,
staging or public HTTPS) and exits non-zero on the first failing section.

Usage:
    python scripts/deploy_check.py --base-url https://pocketscore.example.com
    python scripts/deploy_check.py --base-url http://127.0.0.1:8001 --fixtures tests/fixtures

Checks that need an upload use real fixture files (tone.wav / sample.mid), so a
green run proves the deployed artifact actually stores audio, parses MIDI and
serves both notations - not just that the landing page renders.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:  # pragma: no cover - httpx is a backend dependency
    print("httpx is required: backend/.venv/Scripts/python.exe -m pip install httpx")
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    skipped: bool = False


@dataclass
class Report:
    base_url: str
    checks: List[Check] = field(default_factory=list)

    def record(self, name: str, ok: bool, detail: str = "") -> Check:
        check = Check(name=name, ok=ok, detail=detail)
        self.checks.append(check)
        icon = "PASS" if ok else "FAIL"
        print(f"  [{icon}] {name}" + (f" - {detail}" if detail else ""))
        return check

    def skip(self, name: str, detail: str) -> None:
        self.checks.append(Check(name=name, ok=True, detail=detail, skipped=True))
        print(f"  [SKIP] {name} - {detail}")

    @property
    def failed(self) -> List[Check]:
        return [check for check in self.checks if not check.ok and not check.skipped]


def _error_code(response: httpx.Response) -> Optional[str]:
    try:
        return response.json().get("error", {}).get("code")
    except ValueError:
        return None


def run(base_url: str, fixtures: Path, timeout: float = 30.0) -> Report:
    base = base_url.rstrip("/")
    report = Report(base_url=base)
    headers = {"User-Agent": "PocketScore-DeployCheck/1.0"}

    with httpx.Client(base_url=base, timeout=timeout, headers=headers, follow_redirects=False) as client:
        # ---- 1. liveness --------------------------------------------------
        health = client.get("/api/v1/health")
        body = health.json() if health.status_code == 200 else {}
        caps = body.get("capabilities", {})
        report.record(
            "GET /api/v1/health",
            health.status_code == 200 and body.get("status") == "ok",
            f"HTTP {health.status_code} stage={body.get('stage')} version={body.get('version')}",
        )
        ffmpeg = caps.get("ffmpeg", {})
        report.record(
            "capability: ffmpeg available",
            bool(ffmpeg.get("available")),
            str(ffmpeg.get("version") or "missing")[:60],
        )
        for name in ("mido", "pretty_midi", "mutagen"):
            module = caps.get(name, {})
            report.record(f"capability: {name}", bool(module.get("available")), str(module.get("version")))

        # ---- 2. readiness -------------------------------------------------
        ready = client.get("/api/v1/health/ready")
        ready_body = ready.json() if ready.status_code == 200 else {}
        report.record(
            "GET /api/v1/health/ready",
            ready.status_code == 200 and ready_body.get("status") in {"ready", "degraded"},
            f"HTTP {ready.status_code} status={ready_body.get('status')}",
        )

        # ---- 3. API docs + error envelope --------------------------------
        docs = client.get("/docs")
        report.record("GET /docs", docs.status_code == 200, f"HTTP {docs.status_code}")
        missing = client.get("/api/v1/definitely-not-a-route")
        report.record(
            "unknown API route returns error envelope",
            missing.status_code == 404 and _error_code(missing) == "HTTP_404",
            f"HTTP {missing.status_code} code={_error_code(missing)}",
        )

        # ---- 4. SPA hosting (optional: skipped for API-only deployments) --
        root = client.get("/")
        content_type = root.headers.get("content-type", "")
        if "text/html" in content_type:
            report.record("GET / serves the SPA", root.status_code == 200, f"HTTP {root.status_code}")
            deep_link = client.get("/scores")
            report.record(
                "SPA deep link /scores returns HTML",
                deep_link.status_code == 200 and "text/html" in deep_link.headers.get("content-type", ""),
                f"HTTP {deep_link.status_code}",
            )
        else:
            report.skip("SPA hosting", "API-only deployment (frontend hosted separately)")

        # ---- 5. real upload -> library -> playback ------------------------
        wav = fixtures / "tone.wav"
        if not wav.exists():
            report.record("fixture tone.wav present", False, f"missing {wav}; run scripts/make_fixtures.py")
            return report
        with wav.open("rb") as handle:
            upload = client.post(
                "/api/v1/library/import",
                files={"file": ("deploy-check.wav", handle, "audio/wav")},
                data={"title": "部署验收音", "artist": "DeployCheck"},
                timeout=120.0,
            )
        upload_body = upload.json() if upload.status_code == 201 else {}
        track_id = upload_body.get("track_id")
        report.record(
            "POST /api/v1/library/import (audio uploaded + indexed)",
            upload.status_code == 201 and bool(track_id),
            f"HTTP {upload.status_code} track={track_id} duration={upload_body.get('duration')}",
        )

        if track_id:
            stream = client.get(f"/api/v1/playback/stream/{track_id}")
            stream_body = stream.json() if stream.status_code == 200 else {}
            report.record(
                "GET /api/v1/playback/stream/{track}",
                stream.status_code == 200 and stream_body.get("mode") == "direct",
                f"HTTP {stream.status_code} mode={stream_body.get('mode')}",
            )
            asset_id = (upload_body.get("metadata") or {}).get("audio_asset_id")
            if asset_id:
                ranged = client.get(
                    f"/api/v1/audio/assets/{asset_id}/stream", headers={"Range": "bytes=0-1023"}
                )
                report.record(
                    "audio streaming honours Range",
                    ranged.status_code == 206
                    and len(ranged.content) == 1024
                    and "content-range" in ranged.headers,
                    f"HTTP {ranged.status_code} bytes={len(ranged.content)}",
                )
                waveform = client.get(f"/api/v1/audio/assets/{asset_id}/waveform", params={"buckets": 64})
                peaks = waveform.json().get("peaks", []) if waveform.status_code == 200 else []
                report.record(
                    "waveform returns real peaks",
                    waveform.status_code == 200 and len(peaks) == 64 and max(peaks) > 0.01,
                    f"HTTP {waveform.status_code} buckets={len(peaks)}",
                )

            eligibility = client.get(f"/api/v1/eligibility/{track_id}")
            status = eligibility.json().get("status") if eligibility.status_code == 200 else None
            report.record(
                "eligibility verdict present with reasons",
                eligibility.status_code == 200 and bool(eligibility.json().get("reasons")),
                f"HTTP {eligibility.status_code} status={status}",
            )

        # ---- 6. MIDI -> dual notation ------------------------------------
        midi = fixtures / "sample.mid"
        if not midi.exists():
            report.record("fixture sample.mid present", False, f"missing {midi}; run scripts/make_fixtures.py")
            return report
        with midi.open("rb") as handle:
            imported = client.post(
                "/api/v1/midi/import",
                files={"file": ("deploy-check.mid", handle, "audio/midi")},
                params={"title": "部署验收谱面"},
                timeout=120.0,
            )
        document = imported.json() if imported.status_code == 201 else {}
        document_id = document.get("document_id")
        report.record(
            "POST /api/v1/midi/import (MIDI parsed)",
            imported.status_code == 201 and len(document.get("events") or []) > 0,
            f"HTTP {imported.status_code} events={len(document.get('events') or [])}",
        )

        if document_id:
            dual = client.get(f"/api/v1/notation/{document_id}/both")
            dual_body = dual.json() if dual.status_code == 200 else {}
            grid_notes = dual_body.get("grid", {}).get("stats", {}).get("notes")
            jianpu_notes = dual_body.get("jianpu", {}).get("stats", {}).get("notes")
            report.record(
                "dual notation compiled from one document",
                dual.status_code == 200 and grid_notes == jianpu_notes and grid_notes,
                f"HTTP {dual.status_code} grid={grid_notes} jianpu={jianpu_notes}",
            )

            edit = client.post(
                f"/api/v1/documents/{document_id}/edits",
                json={"operations": [
                    {"op": "add_note", "pitch": 64, "start_time": 0.0, "duration": 1.0}
                ]},
            )
            edit_body = edit.json() if edit.status_code == 200 else {}
            report.record(
                "edit applies to the shared document",
                edit.status_code == 200 and edit_body.get("applied") == 1,
                f"HTTP {edit.status_code} applied={edit_body.get('applied')}",
            )

            svg = client.get(f"/api/v1/notation/{document_id}/grid.svg")
            report.record(
                "grid notation SVG export",
                svg.status_code == 200 and svg.text.startswith("<svg"),
                f"HTTP {svg.status_code} bytes={len(svg.content)}",
            )
            text = client.get(f"/api/v1/notation/{document_id}/jianpu.txt")
            report.record(
                "jianpu text export",
                text.status_code == 200 and "1=C" in text.text,
                f"HTTP {text.status_code} bytes={len(text.content)}",
            )
            midi_export = client.get(f"/api/v1/midi/{document_id}/export")
            report.record(
                "MIDI export returns a real file",
                midi_export.status_code == 200 and midi_export.content[:4] == b"MThd",
                f"HTTP {midi_export.status_code} bytes={len(midi_export.content)}",
            )

        # ---- 7. source catalogue -----------------------------------------
        providers = client.get("/api/v1/sources/providers")
        provider_names = [item["provider"] for item in providers.json().get("items", [])] if providers.status_code == 200 else []
        report.record(
            "GET /api/v1/sources/providers",
            providers.status_code == 200 and "subsonic" in provider_names,
            f"HTTP {providers.status_code} providers={','.join(provider_names)}",
        )
        sources = client.get("/api/v1/sources")
        report.record(
            "local source auto-provisioned",
            sources.status_code == 200 and any(item.get("provider") == "local" for item in sources.json()),
            f"HTTP {sources.status_code} count={len(sources.json()) if sources.status_code == 200 else 0}",
        )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="PocketScore AI deployment acceptance check")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Root URL of the deployed API (default: %(default)s)",
    )
    parser.add_argument(
        "--fixtures",
        default=str(ROOT / "tests" / "fixtures"),
        help="Directory holding tone.wav and sample.mid (default: tests/fixtures)",
    )
    parser.add_argument("--json", action="store_true", help="Print a JSON report instead of the table")
    args = parser.parse_args()

    print(f"PocketScore AI deployment check -> {args.base_url}\n")
    try:
        report = run(args.base_url, Path(args.fixtures))
    except httpx.HTTPError as exc:
        print(f"  [FAIL] could not reach {args.base_url}: {exc}")
        print("\nRESULT: FAIL (unreachable)")
        return 1

    total = len(report.checks)
    failed = report.failed
    skipped = sum(1 for check in report.checks if check.skipped)
    print(f"\n{total - len(failed) - skipped} passed, {skipped} skipped, {len(failed)} failed")

    if args.json:
        print(json.dumps(
            {
                "base_url": report.base_url,
                "checks": [
                    {"name": c.name, "ok": c.ok, "detail": c.detail, "skipped": c.skipped}
                    for c in report.checks
                ],
                "ok": not failed,
            },
            ensure_ascii=False,
            indent=2,
        ))

    if failed:
        print("\nRESULT: FAIL")
        for check in failed:
            print(f"  - {check.name}: {check.detail}")
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
