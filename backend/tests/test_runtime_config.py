"""Runtime / supply-chain configuration assertions (V1.1-C.2.3.4.3).

These are static checks on the files that define how the product is built and
run. They fail loudly when a pin is dropped or a root default comes back.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest


# In CI the test suite runs inside the image with the repo mounted read-only at
# /repo; locally it walks up from the test file.
def _repo_root() -> Path:
    override = os.environ.get("POCKETSCORE_REPO_ROOT")
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    # /tests/x.py has only two parents; parents[2] would raise IndexError.
    return here.parents[2] if len(here.parents) > 2 else here.parent


ROOT = _repo_root()
DOCKERFILE = ROOT / "backend" / "Dockerfile"
WORKFLOW = ROOT / ".github" / "workflows" / "docker-verify.yml"


def dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


# ---------------------------------------------------------------- Dockerfile


def test_runtime_stage_declares_non_root_user() -> None:
    text = dockerfile_text()
    assert re.search(r"^USER 10001:10001$", text, re.M), "runtime must switch to uid 10001"
    # USER must come before CMD
    assert text.index("USER 10001:10001") < text.index("CMD [")


def test_application_user_is_created_with_fixed_ids() -> None:
    text = dockerfile_text()
    assert "--gid 10001" in text and "--uid 10001" in text
    assert "nologin" in text


def test_no_world_writable_directories() -> None:
    text = dockerfile_text()
    assert "chmod 0777" not in text
    assert "chmod -R 777" not in text
    assert "chmod 777" not in text


def test_no_recursive_chown_at_startup() -> None:
    text = dockerfile_text()
    cmd = text[text.index("CMD ["):]
    assert "chown" not in cmd, "the start command must not fix ownership on every boot"


def test_base_images_are_pinned_by_digest() -> None:
    stages = re.findall(r"^FROM (\S+)", dockerfile_text(), re.M)
    assert stages, "no FROM lines found"
    for stage in stages:
        assert "@sha256:" in stage, f"base image is not digest-pinned: {stage}"


def test_proxy_trust_is_not_wildcard() -> None:
    text = dockerfile_text()
    cmd = text[text.index("CMD ["):]
    assert re.search(r"--forwarded-allow-ips=.*127\.0\.0\.1", cmd), cmd
    assert "'*'" not in cmd, "a wildcard proxy must never be the default"
    assert "--forwarded-allow-ips=*" not in cmd


def test_healthcheck_still_targets_health_endpoint() -> None:
    assert "/health" in dockerfile_text()


# ---------------------------------------------------------------- workflow

FLOATING = re.compile(r"uses:\s*[^\s@]+@(v\d+|main|master|latest)\b")


def test_all_actions_are_pinned_to_commit_shas() -> None:
    text = workflow_text()
    uses = re.findall(r"uses:\s*([^\s#]+)", text)
    assert uses, "workflow has no uses: entries"
    for reference in uses:
        if reference.startswith("./"):
            continue
        assert re.search(r"@[0-9a-f]{40}$", reference), f"action not pinned to a SHA: {reference}"


def test_no_floating_major_tags_remain() -> None:
    assert not FLOATING.search(workflow_text())


def test_every_pinned_action_keeps_a_version_comment() -> None:
    for line in workflow_text().splitlines():
        if "uses:" in line and "@" in line and re.search(r"@[0-9a-f]{40}", line):
            assert "#" in line, f"missing version comment: {line.strip()}"


def test_previous_phase_checks_are_still_present() -> None:
    text = workflow_text()
    for required in (
        "test_database_backup.py",
        "test_storage_audit.py",
        "test_project_backup.py",
        "test_project_restore_e2e.py",
        "test_storage_path_safety.py",
        "test_storage_api_security.py",
        "upload_filename",
        "Build image",
        "Verify image contents",
        "Graceful shutdown on SIGTERM",
    ):
        assert required in text, f"previous check disappeared: {required}"


# ---------------------------------------------------------------- settings


def test_cors_lists_are_explicit() -> None:
    from app.core.config import Settings

    settings = Settings()
    assert "*" not in settings.cors_allow_methods
    assert "*" not in settings.cors_allow_headers
    assert "Authorization" in settings.cors_allow_headers
    assert "Range" in settings.cors_allow_headers


def test_trusted_proxies_are_narrow() -> None:
    from app.core.config import Settings

    settings = Settings()
    assert "0.0.0.0/0" not in settings.trusted_proxy_cidrs
    assert "::/0" not in settings.trusted_proxy_cidrs
    assert "127.0.0.1/32" in settings.trusted_proxy_cidrs


def test_rate_limit_defaults_are_positive_and_ordered() -> None:
    from app.core.config import Settings

    settings = Settings()
    assert settings.rate_limit_enabled is None  # environment-driven
    assert settings.rate_limiting_enabled is False  # test env
    assert settings.rate_limit_requests > settings.upload_rate_limit_requests
    assert settings.rate_limit_requests > settings.transcription_rate_limit_requests
    assert settings.upload_rate_limit_window_seconds > 0
    assert settings.rate_limit_max_keys > 0


def test_hsts_is_opt_in() -> None:
    from app.core.config import Settings

    assert Settings().enable_hsts is False


def test_runtime_writable_check_fails_clearly(tmp_path) -> None:
    from app.core.config import Settings

    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    settings = Settings(storage_dir=str(blocker / "storage"))
    with pytest.raises(RuntimeError) as error:
        settings.verify_runtime_writable()
    message = str(error.value)
    assert "not writable" in message
    assert "10001" in message, "the error should name the expected uid"


def test_runtime_writable_check_passes_on_a_writable_dir(tmp_path) -> None:
    from app.core.config import Settings

    settings = Settings(storage_dir=str(tmp_path / "storage"))
    settings.verify_runtime_writable()
    assert (tmp_path / "storage").is_dir()
    assert not list((tmp_path / "storage").glob(".write-probe-*")), "probe file left behind"


# ---------------------------------------------------------------- docker scripts


@pytest.mark.parametrize(
    "script",
    ["test_nonroot_runtime.sh", "test_nonroot_volume.sh"],
)
def test_docker_scripts_exist_and_only_touch_their_own_volume(script: str) -> None:
    path = ROOT / "scripts" / "docker" / script
    text = path.read_text(encoding="utf-8")
    assert "docker volume create" in text
    # deletion must be scoped to the volume created by this run
    for line in text.splitlines():
        if "volume rm" in line:
            assert re.search(r"\$\{?(VOL|vol)", line), f"unscoped volume removal: {line}"
    assert "privileged" not in text
    assert "exit 78" in text, "a missing docker daemon must be reported, not silently passed"
