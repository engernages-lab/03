"""Container-semantics smoke test without Docker (V1.1-C.2).

Runs the exact command the image uses (``python -m uvicorn app.main:app
--host 0.0.0.0 --port $PORT``) as a host process, against a directory that
stands in for the Railway volume, then:

1. waits for ``/health`` and records boot time
2. checks ``/ready`` (model loaded, storage writable, inference limiter)
3. uploads a real WAV and runs a real transcription (no mocks)
4. saves + re-opens the document through the API
5. sends SIGTERM, restarts on the same directory and verifies the data survived

Output is JSON so the report can quote it verbatim.

Usage: python scripts/smoke_deployment.py [--port 8100]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():  # pragma: no cover - POSIX checkout
    PYTHON = ROOT / "backend" / ".venv" / "bin" / "python"
FIXTURE = ROOT / "tests" / "fixtures" / "melody.wav"


def http(url: str, method: str = "GET", data: bytes | None = None, headers: dict | None = None):
    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
        return response.status, json.loads(body) if body else None


def wait_for(url: str, timeout: float) -> float:
    started = time.perf_counter()
    while time.perf_counter() - started < timeout:
        try:
            status, _ = http(url)
            if status == 200:
                return round(time.perf_counter() - started, 2)
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.25)
    raise TimeoutError(f"{url} did not become healthy within {timeout}s")


def spawn(port: int, data_dir: Path, log_path: Path) -> subprocess.Popen:
    env = {
        **os.environ,
        "PORT": str(port),
        "POCKETSCORE_ENVIRONMENT": "staging",
        "POCKETSCORE_DEBUG": "false",
        "POCKETSCORE_LOG_JSON": "true",
        "POCKETSCORE_SESSION_SECRET": "smoke-test-session-secret-value-0123456789",
        "POCKETSCORE_TOKEN_ENCRYPTION_KEY": "c21va2UtdGVzdC1mZXJuZXQta2V5LTMyLWJ5dGVzIQ==",
        "POCKETSCORE_CORS_ORIGINS": "https://engernages-lab.github.io",
        "POCKETSCORE_ALLOW_PRIVATE_NETWORK_SOURCES": "false",
        "POCKETSCORE_DATABASE_URL": f"sqlite:///{(data_dir / 'pocketscore.db').as_posix()}",
        "POCKETSCORE_STORAGE_DIR": str(data_dir / "storage"),
        "POCKETSCORE_MODEL_PRELOAD": "true",
        "POCKETSCORE_MAX_UPLOAD_MB": "25",
    }
    log = open(log_path, "w", encoding="utf-8")
    return subprocess.Popen(
        [
            str(PYTHON), "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(port),
            "--timeout-graceful-shutdown", "10",
        ],
        cwd=str(ROOT / "backend"),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )


def upload_and_transcribe(base: str) -> dict:
    boundary = "----pocketscore-smoke"
    payload = FIXTURE.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="melody.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    status, asset = http(
        f"{base}/api/v1/audio/upload",
        method="POST",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    result = {"upload_status": status, "asset_id": asset.get("asset_id") if asset else None}
    if status >= 300 or not asset:
        return result

    status, job = http(
        f"{base}/api/v1/transcription/jobs",
        method="POST",
        data=json.dumps({"asset_id": asset["asset_id"]}).encode(),
        headers={"Content-Type": "application/json"},
    )
    if status >= 300 or not job:
        result["job_status"] = status
        return result

    started = time.perf_counter()
    status, done = http(f"{base}/api/v1/transcription/jobs/{job['job_id']}/run", method="POST")
    result.update(
        {
            "job_http": status,
            "job_state": (done or {}).get("status"),
            "events": (done or {}).get("events_produced"),
            "document_id": (done or {}).get("document_id"),
            "inference_seconds": round(time.perf_counter() - started, 2),
            "model_load_seconds": ((done or {}).get("analysis") or {}).get("model_load_seconds"),
            "queue_wait_seconds": ((done or {}).get("analysis") or {}).get("queue_wait_seconds"),
        }
    )
    if result["document_id"]:
        status, doc = http(f"{base}/api/v1/documents/{result['document_id']}")
        result["document_status"] = status
        result["document_events"] = len((doc or {}).get("events") or [])
        status, both = http(f"{base}/api/v1/notation/{result['document_id']}/both")
        result["notation_status"] = status
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--keep", action="store_true", help="keep the temp volume directory")
    args = parser.parse_args()

    volume = Path(tempfile.mkdtemp(prefix="pocketscore-volume-"))
    logs = Path(tempfile.mkdtemp(prefix="pocketscore-logs-"))
    report: dict = {"volume_dir": str(volume), "port": args.port}

    process = spawn(args.port, volume, logs / "first.log")
    try:
        report["startup_seconds"] = wait_for(f"http://127.0.0.1:{args.port}/health", timeout=180)
        base = f"http://127.0.0.1:{args.port}"
        status, ready = http(f"{base}/ready")
        report["ready_status"] = status
        report["ready"] = {
            "ready": (ready or {}).get("ready"),
            "model": ((ready or {}).get("checks") or {}).get("model"),
            "storage": ((ready or {}).get("checks") or {}).get("storage"),
            "inference": ((ready or {}).get("checks") or {}).get("inference"),
        }
        report.update(upload_and_transcribe(base))
        report["db_bytes"] = (volume / "pocketscore.db").stat().st_size if (volume / "pocketscore.db").exists() else 0
        audio_files = list((volume / "storage").rglob("*")) if (volume / "storage").exists() else []
        report["stored_files"] = [str(path.relative_to(volume)) for path in audio_files if path.is_file()][:5]
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            code = process.wait(timeout=30)
            # NOTE: on Windows terminate()/SIGTERM maps to TerminateProcess, so
            # the ASGI shutdown hooks do not run here. Linux containers do run
            # them; that path is verified only by the --timeout-graceful-shutdown
            # flag until a real container run exists.
            report["termination_exit_code"] = code
            report["graceful_shutdown_verified"] = False
        except subprocess.TimeoutExpired:  # pragma: no cover - would be a failure
            process.kill()
            report["graceful_exit_code"] = "killed-after-timeout"

    # ---- restart on the same volume: data must survive -------------------
    process = spawn(args.port, volume, logs / "second.log")
    try:
        report["restart_seconds"] = wait_for(f"http://127.0.0.1:{args.port}/health", timeout=180)
        base = f"http://127.0.0.1:{args.port}"
        document_id = report.get("document_id")
        if document_id:
            status, doc = http(f"{base}/api/v1/documents/{document_id}")
            report["after_restart_document_status"] = status
            report["after_restart_events"] = len((doc or {}).get("events") or [])
            report["data_survived"] = status == 200 and report["after_restart_events"] > 0
        status, assets = http(f"{base}/api/v1/audio/assets?limit=5")
        report["after_restart_assets"] = (assets or {}).get("total")
        status, ready = http(f"{base}/ready")
        report["restart_ready"] = (ready or {}).get("ready")
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:  # pragma: no cover
            process.kill()

    report["log_tail"] = (logs / "first.log").read_text(encoding="utf-8", errors="replace").splitlines()[-6:]
    if not args.keep:
        shutil.rmtree(volume, ignore_errors=True)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
