"""Transcription eligibility matrix tests."""

from __future__ import annotations

import pytest

from app.models.source import MusicSourceRecord
from app.services import eligibility, library
from app.services.sources.base import TrackDTO


def _track(db_session, provider: str, *, external_id: str = "ext-1", isrc: str | None = None):
    import uuid

    source = library.create_source(
        db_session,
        provider=provider,
        display_name=f"{provider}-test-{uuid.uuid4().hex[:8]}",
        config={},
    )
    dto = TrackDTO(
        external_id=external_id,
        title="测试曲目",
        artist="测试艺人",
        album="测试专辑",
        duration=200.0,
        metadata={"isrc": isrc} if isrc else {},
        availability="streamable",
    )
    library.upsert_tracks(db_session, source.id, [dto])
    return source, library.get_track(db_session, library.track_pk(source.id, external_id))


def test_spotify_is_always_provider_restricted(db_session):
    _source, track = _track(db_session, "spotify")
    # Even if the user grants every permission, policy wins.
    library.update_permissions(
        db_session,
        track.source_id,
        audio_read_access=True,
        ai_processing_permission=True,
        model_training_permission=True,
    )
    result = eligibility.evaluate(db_session, track, user_confirmed_rights=True)
    assert result.status is eligibility.EligibilityStatus.PROVIDER_RESTRICTED
    assert result.permissions.audio_read_access is False
    assert result.permissions.ai_processing_permission is False
    assert result.permissions.model_training_permission is False
    assert result.ai_allowed is False
    assert any("Spotify" in reason for reason in result.reasons)


def test_apple_music_playback_does_not_imply_transcription(db_session):
    _source, track = _track(db_session, "apple_music")
    result = eligibility.evaluate(db_session, track)
    assert result.status is eligibility.EligibilityStatus.REQUIRES_USER_UPLOAD
    assert result.permissions.playback_access is True
    assert result.permissions.audio_read_access is False
    assert result.ai_allowed is False
    assert any("上传" in reason for reason in result.reasons)


def test_local_track_requires_explicit_ai_permission(db_session):
    _source, track = _track(db_session, "local")
    first = eligibility.evaluate(db_session, track)
    assert first.status is eligibility.EligibilityStatus.REQUIRES_PERMISSION
    assert first.permissions.audio_read_access is True
    assert first.permissions.ai_processing_permission is False

    granted = eligibility.evaluate(db_session, track, user_confirmed_rights=True)
    assert granted.status is eligibility.EligibilityStatus.ELIGIBLE
    assert granted.ai_allowed is True
    # model training stays separate and off by default
    assert granted.permissions.model_training_permission is False


def test_local_permission_persists_after_update(db_session):
    _source, track = _track(db_session, "local", external_id="ext-persist")
    library.update_permissions(db_session, track.source_id, ai_processing_permission=True)
    result = eligibility.evaluate(db_session, track)
    assert result.status is eligibility.EligibilityStatus.ELIGIBLE


def test_subsonic_track_follows_user_permissions(db_session):
    source, track = _track(db_session, "subsonic")
    library.update_permissions(db_session, source.id, ai_processing_permission=True)
    result = eligibility.evaluate(db_session, track)
    assert result.status is eligibility.EligibilityStatus.ELIGIBLE


def test_metadata_denied_means_ineligible(db_session):
    _source, track = _track(db_session, "local", external_id="ext-meta")
    library.update_permissions(db_session, track.source_id, metadata_access=False)
    result = eligibility.evaluate(db_session, track)
    assert result.status is eligibility.EligibilityStatus.INELIGIBLE


@pytest.mark.parametrize("provider", ["netease", "qqmusic"])
def test_unsupported_providers_are_ineligible(db_session, provider):
    _source, track = _track(db_session, provider, external_id=f"ext-{provider}")
    result = eligibility.evaluate(db_session, track)
    assert result.status is eligibility.EligibilityStatus.INELIGIBLE
    assert result.ai_allowed is False
    assert result.reasons


def test_permission_payload_has_all_five_flags(db_session):
    _source, track = _track(db_session, "local", external_id="ext-flags")
    payload = eligibility.evaluate(db_session, track).as_dict()
    for key in (
        "metadata_access",
        "playback_access",
        "audio_read_access",
        "ai_processing_permission",
        "model_training_permission",
    ):
        assert key in payload["permissions"]
    assert payload["status"] in {status.value for status in eligibility.EligibilityStatus}


def test_api_eligibility_endpoint(db_session, client):
    _source, track = _track(db_session, "spotify", external_id="ext-api")
    response = client.get(f"/api/v1/eligibility/{track.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PROVIDER_RESTRICTED"
    assert body["ai_allowed"] is False

    confirmed = client.get(f"/api/v1/eligibility/{track.id}", params={"confirm_rights": True})
    assert confirmed.json()["status"] == "PROVIDER_RESTRICTED"


def test_api_source_summary_counts_verdicts(db_session, client):
    source, _track_local = _track(db_session, "local", external_id="ext-sum")
    response = client.get(f"/api/v1/eligibility/source/{source.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert set(body["counts"]) == {status.value for status in eligibility.EligibilityStatus}
