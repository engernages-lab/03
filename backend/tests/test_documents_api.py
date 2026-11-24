"""API tests for /api/v1/documents (create, read, edit, duplicate, export, delete)."""

from __future__ import annotations

import json

import pytest


@pytest.fixture()
def created_document(client):
    response = client.post(
        "/api/v1/documents",
        json={"title": "API 测试曲", "artist": "QA", "tempo": 90, "key_signature": "G"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_document_returns_full_payload(client):
    response = client.post("/api/v1/documents", json={"title": "新建谱面"})
    assert response.status_code == 201
    body = response.json()
    assert body["document_id"]
    assert body["title"] == "新建谱面"
    assert len(body["tracks"]) == 1
    assert body["events"] == []
    assert body["schema_version"] == 1
    assert body["keyboard_layout"]["key_count"] == 7


def test_create_document_rejects_invalid_tempo(client):
    response = client.post("/api/v1/documents", json={"title": "太快", "tempo": 900})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["fields"]


def test_list_documents_contains_created(client, created_document):
    response = client.get("/api/v1/documents")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    ids = [item["document_id"] for item in body["items"]]
    assert created_document["document_id"] in ids
    item = next(i for i in body["items"] if i["document_id"] == created_document["document_id"])
    assert item["time_signature"] == "4/4"
    assert item["layout_name"]


def test_list_documents_search(client, created_document):
    response = client.get("/api/v1/documents", params={"q": "API 测试"})
    assert response.status_code == 200
    assert any(i["document_id"] == created_document["document_id"] for i in response.json()["items"])


def test_get_single_document(client, created_document):
    response = client.get(f"/api/v1/documents/{created_document['document_id']}")
    assert response.status_code == 200
    assert response.json()["title"] == "API 测试曲"


def test_get_missing_document_returns_typed_error(client):
    response = client.get("/api/v1/documents/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MUSIC_DOCUMENT_NOT_FOUND"


def test_edit_operations_add_and_update_notes(client, created_document):
    document_id = created_document["document_id"]
    response = client.post(
        f"/api/v1/documents/{document_id}/edits",
        json={
            "operations": [
                {"op": "add_note", "pitch": 60, "start_time": 0.0, "duration": 1.0},
                {"op": "add_note", "pitch": 64, "start_time": 0.0, "duration": 1.0},
            ]
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["applied"] == 2
    assert len(result["document"]["events"]) == 2
    assert result["document"]["events"][0]["chord_id"] is not None

    event_id = result["document"]["events"][0]["event_id"]
    response = client.post(
        f"/api/v1/documents/{document_id}/edits",
        json={"operations": [{"op": "update_note", "event_id": event_id, "patch": {"velocity": 30}}]},
    )
    assert response.status_code == 200
    velocities = {e["event_id"]: e["velocity"] for e in response.json()["document"]["events"]}
    assert velocities[event_id] == 30

    response = client.post(
        f"/api/v1/documents/{document_id}/edits",
        json={"operations": [{"op": "delete_note", "event_id": event_id}]},
    )
    assert response.status_code == 200
    assert len(response.json()["document"]["events"]) == 1


def test_edit_operation_validation(client, created_document):
    document_id = created_document["document_id"]
    response = client.post(
        f"/api/v1/documents/{document_id}/edits",
        json={"operations": [{"op": "add_note", "start_time": 0, "duration": 1}]},
    )
    assert response.status_code == 422

    response = client.post(
        f"/api/v1/documents/{document_id}/edits",
        json={"operations": [{"op": "delete_note", "event_id": "ghost"}]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVENT_NOT_FOUND"


def test_patch_document_metadata(client, created_document):
    document_id = created_document["document_id"]
    response = client.patch(
        f"/api/v1/documents/{document_id}",
        json={"title": "改名了", "tempo": 140, "numerator": 3, "denominator": 4},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "改名了"
    assert body["tempo"] == 140
    assert body["time_signature"] == {"numerator": 3, "denominator": 4}


def test_summary_reports_findings(client, created_document):
    document_id = created_document["document_id"]
    client.post(
        f"/api/v1/documents/{document_id}/edits",
        json={"operations": [{"op": "add_note", "pitch": 60, "start_time": 0.0, "duration": 2.0}]},
    )
    response = client.get(f"/api/v1/documents/{document_id}/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["events"] == 1
    assert isinstance(body["findings"], list)
    assert body["tracks"][0]["notes"] == 1


def test_duplicate_document_gets_new_ids(client, created_document):
    document_id = created_document["document_id"]
    client.post(
        f"/api/v1/documents/{document_id}/edits",
        json={"operations": [{"op": "add_note", "pitch": 62, "start_time": 0.0, "duration": 1.0}]},
    )
    response = client.post(f"/api/v1/documents/{document_id}/duplicate")
    assert response.status_code == 201
    clone = response.json()
    assert clone["document_id"] != document_id
    assert clone["title"].endswith("副本")
    assert len(clone["events"]) == 1
    original = client.get(f"/api/v1/documents/{document_id}").json()
    assert clone["events"][0]["event_id"] != original["events"][0]["event_id"]


def test_export_document_returns_json(client, created_document):
    document_id = created_document["document_id"]
    response = client.get(f"/api/v1/documents/{document_id}/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    payload = json.loads(response.text)
    assert payload["document_id"] == document_id

    wrapped = client.get(f"/api/v1/documents/{document_id}/export", params={"format": "pocket"})
    assert wrapped.status_code == 200
    assert json.loads(wrapped.text)["pocketscore"] is True


def test_import_document_roundtrip(client, created_document):
    export = client.get(f"/api/v1/documents/{created_document['document_id']}/export")
    files = {"file": ("doc.json", export.content, "application/json")}
    response = client.post("/api/v1/documents/import", files=files)
    assert response.status_code == 201, response.text
    imported = response.json()
    assert imported["document_id"] != created_document["document_id"]
    assert imported["title"] == created_document["title"]


def test_delete_document_then_404(client):
    created = client.post("/api/v1/documents", json={"title": "待删除"}).json()
    document_id = created["document_id"]
    response = client.delete(f"/api/v1/documents/{document_id}")
    assert response.status_code == 204
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 404


def test_replace_document_rejects_id_mismatch(client, created_document):
    payload = dict(created_document)
    payload["document_id"] = "someone-else"
    response = client.put(f"/api/v1/documents/{created_document['document_id']}", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DOCUMENT_ID_MISMATCH"
