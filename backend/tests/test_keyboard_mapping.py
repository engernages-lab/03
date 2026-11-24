"""Keyboard layout + pitch mapping tests (owner: pocket-keyboard-mapping)."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationAppError
from app.schemas.keyboard import (
    KeyDefinition,
    KeyboardLayout,
    chroma_layout,
    default_layout,
    folded_layout,
)
from app.schemas.music_document import empty_document
from app.services import music_document as core
from app.services.keyboard.mapping import KeyboardMappingEngine, apply_layout, pitch_name


# ---------------------------------------------------------------------------
# mapping engine
# ---------------------------------------------------------------------------

def test_default_layout_maps_natural_scale():
    engine = KeyboardMappingEngine(default_layout())
    expected = {60: "k0", 62: "k1", 64: "k2", 65: "k3", 67: "k4", 69: "k5", 71: "k6"}
    for pitch, key_id in expected.items():
        assert engine.resolve(pitch).key_id == key_id
    assert engine.pitch_for_key("k6") == 71


def test_chromatic_layout_covers_all_twelve_degrees():
    engine = KeyboardMappingEngine(chroma_layout())
    for offset in range(12):
        assert engine.resolve(60 + offset).key_id == f"k{offset}"
    assert engine.resolve(72).key_id is None


def test_folded_layout_reuses_keys_for_higher_octave():
    engine = KeyboardMappingEngine(folded_layout())
    direct = engine.resolve(60)
    assert direct.key_id == "k0"
    assert direct.fallback is False

    # 72 is an explicit key (do') so it must win over folding.
    explicit = engine.resolve(72)
    assert explicit.key_id == "k7"
    assert explicit.fallback is False

    # 84 (C6) has no dedicated key: fold onto the nearest octave-equivalent key.
    folded = engine.resolve(84)
    assert folded.key_id == "k7"
    assert folded.fallback is True


def test_out_of_range_pitch_has_no_key():
    engine = KeyboardMappingEngine(default_layout())
    assert engine.resolve(127).key_id is None
    assert engine.unmapped([60, 61, 127]) == [61, 127]


def test_duplicate_absolute_pitch_rejected():
    keys = [
        KeyDefinition(key_id="a", label="A", index=0, midi_pitch=60),
        KeyDefinition(key_id="b", label="B", index=1, midi_pitch=60),
    ]
    with pytest.raises(ValueError, match="duplicate absolute midi_pitch"):
        KeyboardLayout(layout_id="dup", name="dup", key_count=2, keys=keys)


def test_key_count_mismatch_rejected():
    keys = [KeyDefinition(key_id="a", label="A", index=0, midi_pitch=60)]
    with pytest.raises(ValueError, match="key_count"):
        KeyboardLayout(layout_id="mismatch", name="mismatch", key_count=3, keys=keys)


def test_non_contiguous_index_rejected():
    keys = [
        KeyDefinition(key_id="a", label="A", index=0, midi_pitch=60),
        KeyDefinition(key_id="b", label="B", index=2, midi_pitch=62),
    ]
    with pytest.raises(ValueError, match="contiguous"):
        KeyboardLayout(layout_id="gap", name="gap", key_count=2, keys=keys)


def test_invalid_color_rejected():
    with pytest.raises(ValueError, match="hex"):
        KeyDefinition(key_id="a", label="A", index=0, midi_pitch=60, color="red")


def test_key_needs_a_pitch_source():
    with pytest.raises(ValueError, match="midi_pitch or semitone_offset"):
        KeyDefinition(key_id="a", label="A", index=0)


def test_pitch_name_formatting():
    assert pitch_name(60) == "C4"
    assert pitch_name(69) == "A4"
    assert pitch_name(61) == "C#4"


# ---------------------------------------------------------------------------
# document integration
# ---------------------------------------------------------------------------

def test_layout_change_recomputes_keys_without_touching_pitch():
    document = empty_document(keyboard_layout=default_layout())
    event = core.add_event(document, pitch=65, start_time=0.0, duration=1.0)
    assert event.mapped_key == "k3"

    apply_layout(document, chroma_layout())
    refreshed = document.event_by_id(event.event_id)
    assert refreshed is not None
    assert refreshed.pitch == 65
    assert refreshed.mapped_key == "k5"

    apply_layout(document, default_layout())
    refreshed = document.event_by_id(event.event_id)
    assert refreshed is not None
    assert refreshed.mapped_key == "k3"


def test_unmapped_pitch_keeps_pitch_and_clears_key():
    document = empty_document(keyboard_layout=default_layout())
    event = core.add_event(document, pitch=61, start_time=0.0, duration=1.0)
    assert event.mapped_key is None
    assert event.pitch == 61


def test_move_event_to_key_changes_pitch_only():
    document = empty_document(keyboard_layout=default_layout())
    event = core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    moved = core.move_event_to_key(document, event.event_id, "k4")
    assert moved.pitch == 67
    assert moved.mapped_key == "k4"


def test_move_event_to_unknown_key_raises():
    document = empty_document()
    event = core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    with pytest.raises(ValidationAppError):
        core.move_event_to_key(document, event.event_id, "nope")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def test_list_layouts_includes_builtins(client):
    response = client.get("/api/v1/keyboard-layouts")
    assert response.status_code == 200
    body = response.json()
    ids = {item["layout_id"] for item in body["items"]}
    assert "builtin:7-key-c-major" in ids
    assert "builtin:12-key-chromatic" in ids
    assert body["total"] >= 3


def _custom_layout() -> dict:
    return {
        "layout_id": "test-layout",
        "name": "测试布局",
        "description": "五键",
        "root_note": 60,
        "key_count": 5,
        "octave_span": 1,
        "keys": [
            {"key_id": f"k{i}", "label": f"K{i}", "index": i, "midi_pitch": 60 + i * 2,
             "color": "#3ddc97"}
            for i in range(5)
        ],
    }


def test_create_update_delete_custom_layout(client):
    created = client.post("/api/v1/keyboard-layouts", json=_custom_layout())
    assert created.status_code == 201, created.text
    assert created.json()["key_count"] == 5

    duplicate_id = client.post("/api/v1/keyboard-layouts", json=_custom_layout())
    assert duplicate_id.status_code == 409

    payload = _custom_layout()
    payload["name"] = "改名布局"
    updated = client.put("/api/v1/keyboard-layouts/test-layout", json=payload)
    assert updated.status_code == 200
    assert updated.json()["name"] == "改名布局"

    fetched = client.get("/api/v1/keyboard-layouts/test-layout")
    assert fetched.status_code == 200

    deleted = client.delete("/api/v1/keyboard-layouts/test-layout")
    assert deleted.status_code == 204
    assert client.get("/api/v1/keyboard-layouts/test-layout").status_code == 404


def test_builtin_layout_is_read_only(client):
    layout = default_layout().model_dump(mode="json")
    layout["name"] = "试图改名"
    response = client.put("/api/v1/keyboard-layouts/builtin:7-key-c-major", json=layout)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LAYOUT_READONLY"


def test_duplicate_layout_creates_new_id(client):
    response = client.post(
        "/api/v1/keyboard-layouts/builtin:7-key-c-major/duplicate", json={"name": "我的七键"}
    )
    assert response.status_code == 201
    clone = response.json()
    assert clone["layout_id"].startswith("layout_")
    assert clone["name"] == "我的七键"
    assert clone["is_builtin"] is False
    assert len(clone["keys"]) == 7


def test_preview_and_pitch_map(client):
    preview = client.get("/api/v1/keyboard-layouts/builtin:7-key-c-major/preview")
    assert preview.status_code == 200
    body = preview.json()
    assert len(body["keys"]) == 7
    assert body["keys"][0]["pitch_name"] == "C4"
    assert body["pitch_map"]["60"] == "k0"

    mapping = client.get("/api/v1/keyboard-layouts/builtin:7-key-c-major/pitch-map")
    assert mapping.status_code == 200
    assert mapping.json()["mapping"]["67"] == "k4"


def test_export_import_roundtrip(client):
    exported = client.get("/api/v1/keyboard-layouts/builtin:12-key-chromatic/export")
    assert exported.status_code == 200
    body = exported.json()
    assert body["pocketscore_layout"] is True

    imported = client.post("/api/v1/keyboard-layouts/import", json=body)
    assert imported.status_code == 201
    assert imported.json()["layout_id"].startswith("layout_")
    assert imported.json()["is_builtin"] is False


def test_import_invalid_payload(client):
    response = client.post("/api/v1/keyboard-layouts/import", json={"layout": {"keys": []}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "LAYOUT_IMPORT_INVALID"


def test_restore_default_returns_builtin(client):
    response = client.post("/api/v1/keyboard-layouts/restore-default")
    assert response.status_code == 200
    assert response.json()["layout_id"] == "builtin:7-key-c-major"
    assert response.json()["is_builtin"] is True
