"""Model singleton + startup warm-up contract (V1.1-C.2)."""

from __future__ import annotations

import threading

import pytest

from app.services.audio import model_manager as module
from app.services.audio.model_manager import ModelManager


class FakeModel:
    """Stand-in for basic_pitch.inference.Model (no ONNX session in unit tests)."""

    instances = 0

    def __init__(self, path=None) -> None:
        FakeModel.instances += 1
        self.path = path


@pytest.fixture()
def manager(monkeypatch):
    monkeypatch.setattr(module, "ModelManager", ModelManager)
    instance = ModelManager()
    yield instance
    instance.reset()


def test_load_creates_the_model_once(monkeypatch, manager):
    import basic_pitch
    import basic_pitch.inference as bp_inference

    FakeModel.instances = 0
    monkeypatch.setattr(bp_inference, "Model", FakeModel, raising=False)
    monkeypatch.setattr(basic_pitch, "ICASSP_2022_MODEL_PATH", "fake.onnx", raising=False)

    first = manager.load()
    second = manager.load()

    assert first.status == "ready"
    assert second.status == "ready"
    assert FakeModel.instances == 1, "the model must not be rebuilt on a second call"
    assert manager.get() is manager.get()
    assert first.load_seconds is not None


def test_failed_load_is_reported_and_not_faked(monkeypatch, manager):
    import basic_pitch.inference as bp_inference

    def boom(path=None):
        raise OSError("onnx runtime cannot load this model")

    monkeypatch.setattr(bp_inference, "Model", boom, raising=False)

    state = manager.load()

    assert state.status == "failed"
    assert "onnx runtime" in (state.error or "")
    assert manager.is_ready is False
    with pytest.raises(RuntimeError):
        manager.get()


def test_concurrent_load_only_builds_one_model(monkeypatch, manager):
    import basic_pitch
    import basic_pitch.inference as bp_inference

    FakeModel.instances = 0
    monkeypatch.setattr(bp_inference, "Model", FakeModel, raising=False)
    monkeypatch.setattr(basic_pitch, "ICASSP_2022_MODEL_PATH", "fake.onnx", raising=False)

    threads = [threading.Thread(target=manager.load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert FakeModel.instances == 1
    assert manager.status()["status"] == "ready"


def test_status_shape_is_stable(manager):
    status = manager.status()
    for key in ("status", "model_id", "load_seconds", "warmup_seconds", "runtime", "error"):
        assert key in status
    assert status["status"] == "not_loaded"


def test_reset_clears_state(monkeypatch, manager):
    import basic_pitch
    import basic_pitch.inference as bp_inference

    monkeypatch.setattr(bp_inference, "Model", FakeModel, raising=False)
    monkeypatch.setattr(basic_pitch, "ICASSP_2022_MODEL_PATH", "fake.onnx", raising=False)
    manager.load()
    assert manager.is_ready

    manager.reset()

    assert manager.is_ready is False
    assert manager.status()["status"] == "not_loaded"


def test_inference_calls_are_counted(manager):
    assert manager.inference_calls == 0
    manager.mark_call()
    manager.mark_call()
    assert manager.inference_calls == 2
