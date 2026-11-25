"""Unified library, favourites, playlists, history and playback tests."""

from __future__ import annotations

import io
import math
import struct
import uuid
import wave

import pytest

from app.services import library
from app.services.sources.base import TrackDTO


def make_wav(duration: float = 0.5, sample_rate: int = 22050) -> bytes:
    frames = int(duration * sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        payload = bytearray()
        for index in range(frames):
            value = int(0.4 * 32767 * math.sin(2 * math.pi * 440 * index / sample_rate))
            payload.extend(struct.pack("<h", value))
        handle.writeframes(bytes(payload))
    return buffer.getvalue()


@pytest.fixture()
def imported_track(client):
    response = client.post(
        "/api/v1/library/import",
        files={"file": ("练习曲.wav", make_wav(), "audio/wav")},
        data={"title": "练习曲", "artist": "测试艺人"},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# import + browse
# ---------------------------------------------------------------------------

def test_import_local_audio_creates_track(imported_track):
    assert imported_track["title"] == "练习曲"
    assert imported_track["artist"] == "测试艺人"
    assert imported_track["is_local"] is True
    assert imported_track["source_provider"] == "local"
    assert imported_track["duration"] == pytest.approx(0.5, abs=0.05)
    assert imported_track["stream_url"].startswith("/api/v1/audio/assets/")


def test_track_listing_and_search(client, imported_track):
    listing = client.get("/api/v1/library/tracks")
    assert listing.status_code == 200
    assert any(item["track_id"] == imported_track["track_id"] for item in listing.json()["items"])

    found = client.get("/api/v1/library/tracks", params={"q": "练习"})
    assert found.status_code == 200
    assert found.json()["total"] >= 1

    single = client.get(f"/api/v1/library/tracks/{imported_track['track_id']}")
    assert single.status_code == 200
    assert single.json()["metadata"]["audio_asset_id"]


def test_library_stats_and_albums(client, imported_track):
    stats = client.get("/api/v1/library/stats").json()
    assert stats["tracks"] >= 1
    assert stats["sources"] >= 1

    albums = client.get("/api/v1/library/albums").json()
    assert any(item["album"] == "本地导入" for item in albums["items"])

    artists = client.get("/api/v1/library/artists").json()
    assert any(item["artist"] == "测试艺人" for item in artists["items"])


# ---------------------------------------------------------------------------
# favourites
# ---------------------------------------------------------------------------

def test_favorites_roundtrip(client, imported_track):
    track_id = imported_track["track_id"]
    assert client.post(f"/api/v1/library/favorites/{track_id}").status_code == 204
    listed = client.get("/api/v1/library/favorites").json()
    assert any(item["track_id"] == track_id for item in listed["items"])
    assert client.get(f"/api/v1/library/tracks/{track_id}").json()["is_favorite"] is True

    assert client.delete(f"/api/v1/library/favorites/{track_id}").status_code == 204
    assert client.get(f"/api/v1/library/tracks/{track_id}").json()["is_favorite"] is False


def test_favorite_missing_track(client):
    response = client.post("/api/v1/library/favorites/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TRACK_NOT_FOUND"


# ---------------------------------------------------------------------------
# playlists
# ---------------------------------------------------------------------------

def test_playlist_lifecycle(client, imported_track):
    created = client.post(
        "/api/v1/library/playlists", json={"name": "我的练习", "description": "每天 20 分钟"}
    )
    assert created.status_code == 201
    playlist_id = created.json()["playlist_id"]

    client.post(f"/api/v1/library/playlists/{playlist_id}/tracks/{imported_track['track_id']}")
    tracks = client.get(f"/api/v1/library/playlists/{playlist_id}/tracks").json()
    assert tracks["total"] == 1
    assert tracks["items"][0]["track_id"] == imported_track["track_id"]

    # adding twice must not duplicate
    client.post(f"/api/v1/library/playlists/{playlist_id}/tracks/{imported_track['track_id']}")
    assert client.get(f"/api/v1/library/playlists/{playlist_id}/tracks").json()["total"] == 1

    client.delete(f"/api/v1/library/playlists/{playlist_id}/tracks/{imported_track['track_id']}")
    assert client.get(f"/api/v1/library/playlists/{playlist_id}/tracks").json()["total"] == 0

    listed = client.get("/api/v1/library/playlists").json()
    assert any(item["playlist_id"] == playlist_id for item in listed["items"])

    assert client.delete(f"/api/v1/library/playlists/{playlist_id}").status_code == 204
    assert client.get(f"/api/v1/library/playlists/{playlist_id}/tracks").status_code == 404


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------

def test_history_records_and_clears(client, imported_track):
    response = client.post(
        "/api/v1/library/history",
        json={"track_id": imported_track["track_id"], "position": 12.5, "completed": False},
    )
    assert response.status_code == 201
    history = client.get("/api/v1/library/history").json()
    assert any(item["track"]["track_id"] == imported_track["track_id"] for item in history["items"])

    track = client.get(f"/api/v1/library/tracks/{imported_track['track_id']}").json()
    assert track["play_count"] >= 1

    cleared = client.delete("/api/v1/library/history").json()
    assert cleared["removed"] >= 1


# ---------------------------------------------------------------------------
# merge rules
# ---------------------------------------------------------------------------

def _seed(db_session, provider: str, dto: TrackDTO):
    source = library.create_source(
        db_session, provider=provider, display_name=f"{provider}-{uuid.uuid4().hex[:6]}", config={}
    )
    library.upsert_tracks(db_session, source.id, [dto])
    return source, library.get_track(db_session, library.track_pk(source.id, dto.external_id))


def test_same_title_different_sources_is_not_merged(db_session):
    dto_a = TrackDTO(external_id="a1", title="月光", artist="德彪西", duration=300.0)
    dto_b = TrackDTO(external_id="b1", title="月光", artist="德彪西", duration=300.0)
    _src_a, track_a = _seed(db_session, "subsonic", dto_a)
    _src_b, track_b = _seed(db_session, "apple_music", dto_b)
    assert track_a.id != track_b.id
    # No ISRC -> no canonical group at all (never merge by title).
    assert track_a.canonical_group_id is None
    assert track_b.canonical_group_id is None


def test_same_isrc_groups_metadata(db_session):
    dto_a = TrackDTO(external_id="c1", title="月光", artist="德彪西", duration=300.0,
                     metadata={"isrc": "GBAYC1900001"})
    dto_b = TrackDTO(external_id="d1", title="Clair de Lune", artist="Debussy", duration=305.0,
                     metadata={"isrc": "gbayc1900001"})
    _src_a, track_a = _seed(db_session, "subsonic", dto_a)
    _src_b, track_b = _seed(db_session, "apple_music", dto_b)
    assert track_a.canonical_group_id == track_b.canonical_group_id
    # grouping is metadata only - ids stay distinct
    assert track_a.id != track_b.id


def test_duplicate_external_id_updates_existing(db_session):
    dto = TrackDTO(external_id="dup-1", title="原始标题", artist="A", duration=100.0)
    source, track = _seed(db_session, "subsonic", dto)
    library.upsert_tracks(
        db_session, source.id,
        [TrackDTO(external_id="dup-1", title="更新标题", artist="A", duration=100.0)],
    )
    refreshed = library.get_track(db_session, library.track_pk(source.id, "dup-1"))
    assert refreshed.id == track.id
    assert refreshed.title == "更新标题"


# ---------------------------------------------------------------------------
# playback
# ---------------------------------------------------------------------------

def test_stream_info_for_local_track(client, imported_track):
    response = client.get(f"/api/v1/playback/stream/{imported_track['track_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "local"
    assert body["mode"] == "direct"
    assert body["url"].startswith("/api/v1/audio/assets/")


def test_stream_info_missing_track(client):
    response = client.get("/api/v1/playback/stream/nope")
    assert response.status_code == 404


def test_spotify_proxy_is_forbidden(client, db_session):
    dto = TrackDTO(external_id="sp-1", title="Song", artist="Artist", duration=200.0)
    source, _track = _seed(db_session, "spotify", dto)
    response = client.get(f"/api/v1/playback/proxy/{source.id}/sp-1")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PROVIDER_RESTRICTED"

def test_ensure_local_source_is_idempotent(db_session):
    """Concurrent first-use requests must not surface a UNIQUE violation."""
    from sqlalchemy import func, select

    from app.models.source import MusicSourceRecord

    first = library.ensure_local_source(db_session)
    second = library.ensure_local_source(db_session)
    assert first.id == second.id == library.LOCAL_SOURCE_ID
    count = db_session.execute(
        select(func.count())
        .select_from(MusicSourceRecord)
        .where(
            MusicSourceRecord.provider == "local",
            # the built-in source is identified by this exact pair; other tests
            # may register additional local-provider sources in the shared DB
            MusicSourceRecord.display_name == "本地音乐",
        )
    ).scalar()
    assert count == 1
