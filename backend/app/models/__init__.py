"""ORM model registry.

Importing this package registers every mapper with ``Base.metadata`` so that
``init_db()`` and Alembic autogenerate can see the full schema.  Models are
added here as each development stage lands.
"""

from app.models.audio import AudioAssetRecord
from app.models.base import IdMixin, TimestampMixin, utcnow
from app.models.music import (
    KeyboardLayoutRecord,
    MusicDocumentRecord,
    MusicEventRecord,
    MusicTrackRecord,
)
from app.models.source import (
    ExternalAccountRecord,
    FavoriteRecord,
    MusicSourcePermissionRecord,
    MusicSourceRecord,
    PlaybackHistoryRecord,
    PlaylistTrackRecord,
    TranscriptionJobRecord,
    UnifiedAlbumRecord,
    UnifiedArtistRecord,
    UnifiedPlaylistRecord,
    UnifiedTrackRecord,
)

__all__ = [
    "IdMixin", "TimestampMixin", "utcnow",
    "AudioAssetRecord",
    "KeyboardLayoutRecord", "MusicDocumentRecord", "MusicEventRecord", "MusicTrackRecord",
    "ExternalAccountRecord", "FavoriteRecord", "MusicSourcePermissionRecord",
    "MusicSourceRecord", "PlaybackHistoryRecord", "PlaylistTrackRecord",
    "TranscriptionJobRecord", "UnifiedAlbumRecord", "UnifiedArtistRecord",
    "UnifiedPlaylistRecord", "UnifiedTrackRecord",
]
