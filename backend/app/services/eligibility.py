"""Transcription eligibility: five independent permissions, six verdicts.

Owner: pocket-music-source skill.  This is the only gate between a track and the
AI pipeline.  Provider policy always wins over user permission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.source import MusicSourcePermissionRecord, MusicSourceRecord, UnifiedTrackRecord
from app.services import library


class EligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    REQUIRES_USER_UPLOAD = "REQUIRES_USER_UPLOAD"
    REQUIRES_PERMISSION = "REQUIRES_PERMISSION"
    PROVIDER_RESTRICTED = "PROVIDER_RESTRICTED"
    UNKNOWN = "UNKNOWN"


@dataclass
class TranscriptionPermissions:
    metadata_access: bool = False
    playback_access: bool = False
    audio_read_access: bool = False
    ai_processing_permission: bool = False
    model_training_permission: bool = False

    def as_dict(self) -> Dict[str, bool]:
        return {
            "metadata_access": self.metadata_access,
            "playback_access": self.playback_access,
            "audio_read_access": self.audio_read_access,
            "ai_processing_permission": self.ai_processing_permission,
            "model_training_permission": self.model_training_permission,
        }


@dataclass
class EligibilityResult:
    track_id: str
    provider: str
    status: EligibilityStatus
    permissions: TranscriptionPermissions
    reasons: List[str] = field(default_factory=list)
    policy_note: str = ""

    @property
    def ai_allowed(self) -> bool:
        return self.status == EligibilityStatus.ELIGIBLE

    def as_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "provider": self.provider,
            "status": self.status.value,
            "permissions": self.permissions.as_dict(),
            "reasons": self.reasons,
            "policy_note": self.policy_note,
            "ai_allowed": self.ai_allowed,
        }


#: Provider policy overrides.  ``None`` means "decided by stored permissions".
PROVIDER_POLICY: Dict[str, Dict[str, Any]] = {
    "spotify": {
        "restricted": True,
        "audio_read_access": False,
        "ai_processing_permission": False,
        "model_training_permission": False,
        "reason": (
            "Spotify 开发者政策禁止分析 Spotify 内容或将其输入 AI/机器学习模型，"
            "因此该曲目永远不进入扒谱流程。"
        ),
        "note": "Spotify 内容被平台政策限制（PROVIDER_RESTRICTED）。",
    },
    "apple_music": {
        "restricted": False,
        "audio_read_access": False,
        "ai_processing_permission": False,
        "reason": (
            "Apple Music 仅通过 MusicKit 授权播放，PocketScore 不读取其音频流；"
            "若要扒谱，请上传你拥有处理权的音频文件。"
        ),
        "note": "播放可用不等于可扒谱。",
    },
    "netease": {
        "restricted": False,
        "unsupported": True,
        "reason": "网易云音乐暂无官方第三方接口，无法获取内容。",
    },
    "qqmusic": {
        "restricted": False,
        "unsupported": True,
        "reason": "QQ 音乐暂无官方第三方接口，无法获取内容。",
    },
}


def _permissions_from_row(row: Optional[MusicSourcePermissionRecord]) -> TranscriptionPermissions:
    if row is None:
        return TranscriptionPermissions()
    return TranscriptionPermissions(
        metadata_access=row.metadata_access,
        playback_access=row.playback_access,
        audio_read_access=row.audio_read_access,
        ai_processing_permission=row.ai_processing_permission,
        model_training_permission=row.model_training_permission,
    )


def evaluate(
    session: Session,
    track: UnifiedTrackRecord,
    *,
    user_confirmed_rights: bool = False,
) -> EligibilityResult:
    source = session.get(MusicSourceRecord, track.source_id)
    provider = source.provider if source else "unknown"
    permission_row = session.execute(
        __import__("sqlalchemy").select(MusicSourcePermissionRecord).where(
            MusicSourcePermissionRecord.source_id == track.source_id
        )
    ).scalars().first()
    permissions = _permissions_from_row(permission_row)
    policy = PROVIDER_POLICY.get(provider, {})
    reasons: List[str] = []

    # 1. Platform policy is absolute.
    if policy.get("restricted"):
        permissions.audio_read_access = False
        permissions.ai_processing_permission = False
        permissions.model_training_permission = False
        reasons.append(policy["reason"])
        return EligibilityResult(
            track_id=track.id,
            provider=provider,
            status=EligibilityStatus.PROVIDER_RESTRICTED,
            permissions=permissions,
            reasons=reasons,
            policy_note=policy.get("note", ""),
        )

    if policy.get("unsupported"):
        reasons.append(policy["reason"])
        return EligibilityResult(
            track_id=track.id,
            provider=provider,
            status=EligibilityStatus.INELIGIBLE,
            permissions=permissions,
            reasons=reasons,
            policy_note="该平台没有可用的官方接口。",
        )

    if policy.get("audio_read_access") is False:
        permissions.audio_read_access = False
        permissions.ai_processing_permission = False
    if not permissions.metadata_access:
        reasons.append("该来源没有元数据访问权限。")
        return EligibilityResult(
            track_id=track.id, provider=provider, status=EligibilityStatus.INELIGIBLE,
            permissions=permissions, reasons=reasons,
        )

    # 2. Audio bytes must be readable at all.
    if not permissions.audio_read_access:
        reasons.append(policy.get("reason") or "该来源不允许读取原始音频。")
        reasons.append("请上传你拥有处理权的音频文件后再进行扒谱。")
        return EligibilityResult(
            track_id=track.id, provider=provider,
            status=EligibilityStatus.REQUIRES_USER_UPLOAD,
            permissions=permissions, reasons=reasons,
            policy_note=policy.get("note", ""),
        )

    # 3. Explicit user permission for AI processing (separate from playback).
    if user_confirmed_rights:
        permissions.ai_processing_permission = True
    if not permissions.ai_processing_permission:
        reasons.append("该音频允许播放，但尚未获得用于 AI 扒谱的授权。")
        reasons.append("请在音乐来源页面确认你对这些音频拥有处理权。")
        return EligibilityResult(
            track_id=track.id, provider=provider,
            status=EligibilityStatus.REQUIRES_PERMISSION,
            permissions=permissions, reasons=reasons,
        )

    reasons.append("元数据、播放、音频读取与 AI 处理权限均已满足。")
    if not permissions.model_training_permission:
        reasons.append("模型训练权限未授予（与单次处理权限分开管理）。")
    return EligibilityResult(
        track_id=track.id, provider=provider, status=EligibilityStatus.ELIGIBLE,
        permissions=permissions, reasons=reasons,
    )


def evaluate_by_track_id(
    session: Session, track_id: str, *, user_confirmed_rights: bool = False
) -> EligibilityResult:
    track = library.get_track(session, track_id)
    return evaluate(session, track, user_confirmed_rights=user_confirmed_rights)


def summarize_for_source(session: Session, source_id: str) -> Dict[str, Any]:
    """Distribution of verdicts across a source's tracks (for the UI)."""
    from sqlalchemy import select

    tracks = list(
        session.execute(
            select(UnifiedTrackRecord).where(UnifiedTrackRecord.source_id == source_id)
        ).scalars()
    )
    counts: Dict[str, int] = {status.value: 0 for status in EligibilityStatus}
    for track in tracks:
        result = evaluate(session, track)
        counts[result.status.value] += 1
    return {"source_id": source_id, "total": len(tracks), "counts": counts}
