"""Dual-format synchronisation tests.

Both notations are compiled from the same MusicDocument, so every edit must be
visible in both views, and a layout change must only move key labels.
"""

from __future__ import annotations

import pytest


def create_document(client, title: str = "同步测试") -> str:
    return client.post("/api/v1/documents", json={"title": title}).json()["document_id"]


def apply(client, document_id: str, *operations, expect: int = 200):
    response = client.post(
        f"/api/v1/documents/{document_id}/edits", json={"operations": list(operations)}
    )
    assert response.status_code == expect, response.text
    return response.json() if expect == 200 else response


def views(client, document_id: str):
    response = client.get(f"/api/v1/notation/{document_id}/both")
    assert response.status_code == 200, response.text
    return response.json()


def jianpu_tokens(view) -> list:
    return [note["token"] for measure in view["jianpu"]["measures"] for note in measure["notes"]]


def grid_cells(view, key_id: str) -> list:
    row = next(r for r in view["grid"]["rows"] if r["key_id"] == key_id)
    return row["cells"]


# ---------------------------------------------------------------------------
# edit -> both views
# ---------------------------------------------------------------------------

def test_added_note_appears_in_both_notations(client):
    document_id = create_document(client)
    before = views(client, document_id)
    assert before["grid"]["stats"]["notes"] == 0
    assert before["jianpu"]["stats"]["notes"] == 0

    result = apply(client, document_id, {"op": "add_note", "pitch": 60, "start_time": 0.0, "duration": 1.0})
    event_id = result["document"]["events"][0]["event_id"]

    after = views(client, document_id)
    assert after["grid"]["stats"]["notes"] == 1
    assert after["jianpu"]["stats"]["notes"] == 1
    assert grid_cells(after, "k0")[0]["event_id"] == event_id
    tokens = jianpu_tokens(after)
    assert tokens == ["1"]
    assert after["jianpu"]["measures"][0]["notes"][0]["event_id"] == event_id


def test_pitch_change_moves_grid_row_and_changes_token(client):
    document_id = create_document(client)
    created = apply(client, document_id, {"op": "add_note", "pitch": 60, "start_time": 0.0, "duration": 1.0})
    event_id = created["document"]["events"][0]["event_id"]
    assert jianpu_tokens(views(client, document_id)) == ["1"]

    apply(client, document_id, {"op": "update_note", "event_id": event_id, "patch": {"pitch": 67}})

    after = views(client, document_id)
    assert jianpu_tokens(after) == ["5"]
    assert grid_cells(after, "k0")[0]["state"] == "empty"
    assert grid_cells(after, "k4")[0]["state"] == "note"
    assert after["grid"]["stats"]["notes"] == 1


def test_duration_change_keeps_both_in_step(client):
    document_id = create_document(client)
    created = apply(client, document_id, {"op": "add_note", "pitch": 62, "start_time": 0.0, "duration": 1.0})
    event_id = created["document"]["events"][0]["event_id"]

    apply(client, document_id, {"op": "update_note", "event_id": event_id, "patch": {"duration": 2.0}})
    after = views(client, document_id)
    assert grid_cells(after, "k1")[0]["span"] == 8
    assert after["jianpu"]["measures"][0]["notes"][0]["duration_label"] == "-"


def test_delete_removes_from_both(client):
    document_id = create_document(client)
    created = apply(client, document_id, {"op": "add_note", "pitch": 60, "start_time": 0.0, "duration": 1.0})
    event_id = created["document"]["events"][0]["event_id"]
    apply(client, document_id, {"op": "delete_note", "event_id": event_id})

    after = views(client, document_id)
    assert after["grid"]["stats"]["notes"] == 0
    assert after["jianpu"]["stats"]["notes"] == 0
    assert all(cell["state"] == "empty" for row in after["grid"]["rows"] for cell in row["cells"])


def test_rest_edit_updates_rest_lane_and_zero_token(client):
    document_id = create_document(client)
    apply(client, document_id, {"op": "add_rest", "start_time": 0.0, "duration": 1.0})
    after = views(client, document_id)
    assert after["grid"]["rest_row"] is not None
    assert after["grid"]["rest_row"]["cells"][0]["state"] == "rest"
    assert jianpu_tokens(after) == ["0"]


def test_tempo_change_propagates_to_both_headers(client):
    document_id = create_document(client)
    apply(client, document_id, {"op": "set_tempo", "tempo": 84.0})
    after = views(client, document_id)
    assert after["grid"]["tempo"] == pytest.approx(84.0)
    assert after["jianpu"]["tempo"] == pytest.approx(84.0)
    assert after["document"]["tempo"] == pytest.approx(84.0)


def test_time_signature_change_reshapes_grid_and_measures(client):
    document_id = create_document(client)
    apply(client, document_id, {"op": "add_note", "pitch": 60, "start_time": 6.0, "duration": 1.0})
    before = views(client, document_id)
    assert before["grid"]["slots_per_measure"] == 16
    # beat 6 in 4/4 is measure 2, beat 3
    assert before["jianpu"]["measures"][1]["notes"][0]["beat_in_measure"] == 3.0

    apply(client, document_id, {"op": "set_time_signature", "numerator": 3, "denominator": 4})
    after = views(client, document_id)
    assert after["grid"]["slots_per_measure"] == 12
    assert after["jianpu"]["time_signature"] == "3/4"
    # beat 7 in 3/4 belongs to measure 3
    assert after["jianpu"]["measures"][2]["notes"][0]["beat_in_measure"] == 1.0


# ---------------------------------------------------------------------------
# layout changes
# ---------------------------------------------------------------------------

def test_layout_change_updates_key_labels_but_not_pitches(client):
    document_id = create_document(client)
    created = apply(
        client, document_id,
        {"op": "add_note", "pitch": 61, "start_time": 0.0, "duration": 1.0},
    )
    event_id = created["document"]["events"][0]["event_id"]

    before = views(client, document_id)
    assert before["grid"]["stats"]["unmapped"] == 1
    assert before["jianpu"]["measures"][0]["notes"][0]["mapped_key"] is None

    chromatic = client.get("/api/v1/keyboard-layouts/builtin:12-key-chromatic").json()
    apply(client, document_id, {"op": "set_layout", "layout": chromatic})

    after = views(client, document_id)
    assert after["grid"]["stats"]["unmapped"] == 0
    assert after["grid"]["layout_id"] == "builtin:12-key-chromatic"
    note = after["jianpu"]["measures"][0]["notes"][0]
    assert note["event_id"] == event_id
    assert note["pitch"] == 61                # pitch untouched
    assert note["key_label"] == "C#4"          # label follows the layout
    assert note["token"] == "#1"
    assert grid_cells(after, "k1")[0]["state"] == "note"


def test_both_views_use_same_layout_override(client):
    document_id = create_document(client)
    apply(client, document_id, {"op": "add_note", "pitch": 61, "start_time": 0.0, "duration": 1.0})

    response = client.get(
        f"/api/v1/notation/{document_id}/both",
        params={"layout_id": "builtin:12-key-chromatic"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["grid"]["layout_id"] == "builtin:12-key-chromatic"
    assert body["jianpu"]["layout_id"] == "builtin:12-key-chromatic"
    assert body["grid"]["stats"]["unmapped"] == 0
    assert body["jianpu"]["measures"][0]["notes"][0]["key_label"] == "C#4"


# ---------------------------------------------------------------------------
# undo / redo (document snapshots) and atomicity
# ---------------------------------------------------------------------------

def test_undo_restores_both_notations_exactly(client):
    document_id = create_document(client)
    apply(client, document_id, {"op": "add_note", "pitch": 60, "start_time": 0.0, "duration": 1.0})
    snapshot = client.get(f"/api/v1/documents/{document_id}").json()
    baseline = views(client, document_id)

    apply(client, document_id, {"op": "add_note", "pitch": 64, "start_time": 1.0, "duration": 1.0})
    changed = views(client, document_id)
    assert changed["grid"]["stats"]["notes"] == 2

    # Undo = restore the snapshot through the same document endpoint.
    restored = client.put(f"/api/v1/documents/{document_id}", json=snapshot)
    assert restored.status_code == 200
    after = views(client, document_id)
    assert after["grid"]["stats"] == baseline["grid"]["stats"]
    assert jianpu_tokens(after) == jianpu_tokens(baseline)


def test_failed_batch_leaves_document_untouched(client):
    document_id = create_document(client)
    apply(client, document_id, {"op": "add_note", "pitch": 60, "start_time": 0.0, "duration": 1.0})
    before = views(client, document_id)

    apply(
        client, document_id,
        {"op": "add_note", "pitch": 62, "start_time": 1.0, "duration": 1.0},
        {"op": "delete_note", "event_id": "ghost"},
        expect=404,
    )
    after = views(client, document_id)
    assert after["grid"]["stats"] == before["grid"]["stats"]


def test_move_note_rewrites_pitch_from_key(client):
    document_id = create_document(client)
    created = apply(client, document_id, {"op": "add_note", "pitch": 60, "start_time": 0.0, "duration": 1.0})
    event_id = created["document"]["events"][0]["event_id"]

    apply(client, document_id, {"op": "move_note", "event_id": event_id, "key_id": "k6"})
    after = views(client, document_id)
    assert after["document"]["events"][0]["pitch"] == 71
    assert jianpu_tokens(after) == ["7"]
    assert grid_cells(after, "k6")[0]["state"] == "note"


def test_chord_renders_in_both_notations(client):
    document_id = create_document(client)
    apply(
        client, document_id,
        {"op": "add_note", "pitch": 60, "start_time": 0.0, "duration": 1.0},
        {"op": "add_note", "pitch": 64, "start_time": 0.0, "duration": 1.0},
        {"op": "add_note", "pitch": 67, "start_time": 0.0, "duration": 1.0},
    )
    after = views(client, document_id)
    assert after["grid"]["stats"]["chords"] == 1
    assert after["jianpu"]["stats"]["chords"] == 1
    notes = after["jianpu"]["measures"][0]["notes"]
    assert [n["chord_index"] for n in notes] == [0, 1, 2]
    active_rows = [row for row in after["grid"]["rows"] if row["cells"][0]["state"] == "note"]
    assert len(active_rows) == 3


def test_findings_are_reported(client):
    document_id = create_document(client)
    apply(
        client, document_id,
        {"op": "add_note", "pitch": 60, "start_time": 0.0, "duration": 2.0},
        {"op": "add_note", "pitch": 60, "start_time": 1.0, "duration": 2.0},
    )
    body = views(client, document_id)
    codes = {finding["code"] for finding in body["findings"]}
    assert "EVENT_OVERLAP" in codes
