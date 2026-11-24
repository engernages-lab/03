"""Music source endpoints: catalogue, connection, sync, candidates."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import ValidationAppError
from app.core.timeutils import as_utc
from app.models.source import MusicSourceRecord
from app.services import library
from app.services.sources import registry
from app.services.sources.base import ConnectionResult
from app.services.sources.registry import USER_CREATABLE

router = APIRouter()


class SourceCreateRequest(BaseModel):
    provider: str = Field(min_length=2, max_length=32)
    display_name: Optional[str] = Field(default=None, max_length=120)
    # subsonic / navidrome
    server_url: Optional[str] = Field(default=None, max_length=500)
    username: Optional[str] = Field(default=None, max_length=120)
    password: Optional[str] = Field(default=None, max_length=256)
    # apple music
    team_id: Optional[str] = None
    key_id: Optional[str] = None
    private_key_path: Optional[str] = None
    storefront: Optional[str] = None
    # spotify
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: Optional[str] = None


class PermissionsUpdate(BaseModel):
    # `model_*` fields are legitimate here; disable Pydantic's namespace guard.
    model_config = ConfigDict(protected_namespaces=())

    metadata_access: Optional[bool] = None
    playback_access: Optional[bool] = None
    audio_read_access: Optional[bool] = None
    ai_processing_permission: Optional[bool] = None
    model_training_permission: Optional[bool] = None


class SourceOut(BaseModel):
    source_id: str
    provider: str
    display_name: str
    status: str
    connected_at: Optional[datetime]
    last_error: Optional[str]
    capabilities: Dict[str, Any]
    policy_note: str
    account_name: Optional[str]
    is_local: bool


def _source_out(session: Session, record: MusicSourceRecord) -> SourceOut:
    adapter = registry.build_adapter(record, session=session)
    account = record.account
    return SourceOut(
        source_id=record.id,
        provider=record.provider,
        display_name=record.display_name,
        status=record.status,
        connected_at=as_utc(record.connected_at),
        last_error=record.last_error,
        capabilities=adapter.capability_report(),
        policy_note=adapter.capabilities.policy_note,
        account_name=account.account_name if account else None,
        is_local=record.provider == "local",
    )


@router.get("/providers")
def list_providers() -> Dict[str, Any]:
    return {
        "items": registry.provider_list(),
        "creatable": list(USER_CREATABLE),
    }


@router.get("", response_model=List[SourceOut])
def list_sources(db: Session = Depends(get_db)) -> List[SourceOut]:
    return [_source_out(db, record) for record in library.list_sources(db)]


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def create_source(payload: SourceCreateRequest, db: Session = Depends(get_db)) -> SourceOut:
    provider = payload.provider
    if provider not in USER_CREATABLE:
        raise ValidationAppError(
            f"provider {provider!r} cannot be created manually",
            code="PROVIDER_NOT_CREATABLE",
            details={"creatable": list(USER_CREATABLE)},
        )

    config: Dict[str, Any] = {}
    display_name = payload.display_name or registry.PROVIDER_INFO[provider]["display_name"]

    if provider == "subsonic":
        if not payload.server_url or not payload.username or not payload.password:
            raise ValidationAppError(
                "server_url, username and password are required",
                code="SOURCE_CONFIG_INVALID",
            )
        from app.core.ssrf import validate_server_url

        validated = validate_server_url(payload.server_url)
        config = {
            "base_url": validated.normalized,
            "username": payload.username,
            "password": payload.password,
        }
        display_name = payload.display_name or f"Navidrome · {validated.host}"
    elif provider == "apple_music":
        config = {
            "team_id": payload.team_id,
            "key_id": payload.key_id,
            "private_key_path": payload.private_key_path,
            "storefront": payload.storefront or "us",
        }
        config = {k: v for k, v in config.items() if v}
    elif provider == "spotify":
        config = {
            "client_id": payload.client_id,
            "client_secret": payload.client_secret,
            "redirect_uri": payload.redirect_uri,
        }
        config = {k: v for k, v in config.items() if v}

    record = library.create_source(db, provider=provider, display_name=display_name, config=config)
    return _source_out(db, record)


@router.get("/{source_id}", response_model=SourceOut)
def get_source(source_id: str, db: Session = Depends(get_db)) -> SourceOut:
    return _source_out(db, library.get_source(db, source_id))


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_source(source_id: str, db: Session = Depends(get_db)) -> Response:
    if source_id == library.LOCAL_SOURCE_ID:
        raise ValidationAppError(
            "the local source cannot be deleted", code="SOURCE_READONLY", status_code=403
        )
    library.delete_source(db, source_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{source_id}/test")
async def test_connection(source_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    record = library.get_source(db, source_id)
    adapter = registry.build_adapter(record, session=db)
    result: ConnectionResult = await adapter.test_connection()

    record.status = result.status
    record.last_error = None if result.ok else result.message
    if result.ok:
        record.connected_at = datetime.utcnow()
        # Persist hashed credentials instead of the plain password.
        if record.provider == "subsonic" and hasattr(adapter, "auth_signature"):
            config = record.config
            config.pop("password", None)
            config.update(adapter.auth_signature())
            record.config_json = json.dumps(config, ensure_ascii=False)
    db.commit()

    return {
        "ok": result.ok,
        "status": result.status,
        "message": result.message,
        "server_version": result.server_version,
        "account_name": result.account_name,
        "details": result.details,
    }


@router.post("/{source_id}/sync")
async def sync_source(source_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Pull the provider library into the unified index."""
    record = library.get_source(db, source_id)
    adapter = registry.build_adapter(record, session=db)

    connection = await adapter.test_connection()
    if not connection.ok:
        record.status = connection.status
        record.last_error = connection.message
        db.commit()
        return {"ok": False, "status": connection.status, "message": connection.message}

    tracks: List[Any] = []
    page = await adapter.list_tracks(limit=200)
    tracks.extend(page.items)
    if not tracks:
        for playlist in await adapter.list_playlists():
            result = await adapter.get_playlist_tracks(playlist.external_id, limit=200)
            tracks.extend(result.items)
            if len(tracks) >= 500:
                break

    stats = library.sync_from_dtos(db, record.id, tracks)
    record.status = "connected"
    record.connected_at = datetime.utcnow()
    record.last_error = None
    record.capabilities_json = json.dumps(adapter.capability_report(), ensure_ascii=False)
    db.commit()
    return {"ok": True, **stats, "message": f"已同步 {stats['total']} 首曲目"}


@router.get("/{source_id}/permissions")
def get_permissions(source_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    record = library.get_permissions(db, source_id)
    return {
        "source_id": source_id,
        "metadata_access": record.metadata_access,
        "playback_access": record.playback_access,
        "audio_read_access": record.audio_read_access,
        "ai_processing_permission": record.ai_processing_permission,
        "model_training_permission": record.model_training_permission,
        "notes": record.notes,
    }


@router.get("/{source_id}/apple/developer-token")
def apple_developer_token(source_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Mint the ES256 developer token MusicKit needs (Apple Music only).

    The token itself is short-lived (24h) and only grants access to the Apple
    Music catalog API for this app; the user's own authorisation still comes
    from MusicKit in the browser.
    """
    record = library.get_source(db, source_id)
    if record.provider != "apple_music":
        raise ValidationAppError(
            "this endpoint only serves Apple Music sources", code="PROVIDER_MISMATCH"
        )
    adapter = registry.build_adapter(record, session=db)
    token = adapter.developer_token()  # raises PROVIDER_NOT_CONFIGURED when incomplete
    return {
        "developer_token": token,
        "storefront": getattr(adapter, "storefront", None),
        "expires_in": 86_400,
        "usage": "MusicKit.configure({ developerToken, app: { name, build } })",
    }


@router.get("/{source_id}/spotify/authorize-url")
def spotify_authorize_url(
    source_id: str, state: Optional[str] = Query(default=None), db: Session = Depends(get_db)
) -> Dict[str, Any]:
    record = library.get_source(db, source_id)
    if record.provider != "spotify":
        raise ValidationAppError(
            "this endpoint only serves Spotify sources", code="PROVIDER_MISMATCH"
        )
    from app.core.crypto import encode_state

    adapter = registry.build_adapter(record, session=db)
    oauth_state = state or encode_state(source_id)
    return {
        "authorize_url": adapter.authorize_url(oauth_state),
        "state": oauth_state,
        "scopes": list(getattr(adapter, "SCOPES", [])) or None,
        "note": "Spotify 授权后仅使用元数据与官方播放控制；AI 分析被平台政策禁止。",
    }


@router.put("/{source_id}/permissions")
def update_permissions(
    source_id: str, payload: PermissionsUpdate, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    library.get_source(db, source_id)
    record = library.update_permissions(
        db,
        source_id,
        metadata_access=payload.metadata_access,
        playback_access=payload.playback_access,
        audio_read_access=payload.audio_read_access,
        ai_processing_permission=payload.ai_processing_permission,
        model_training_permission=payload.model_training_permission,
    )
    return {
        "source_id": source_id,
        "metadata_access": record.metadata_access,
        "playback_access": record.playback_access,
        "audio_read_access": record.audio_read_access,
        "ai_processing_permission": record.ai_processing_permission,
        "model_training_permission": record.model_training_permission,
    }
