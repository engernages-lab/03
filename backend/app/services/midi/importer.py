"""MIDI import: .mid/.midi -> MusicDocument.

Owner: pocket-audio-transcription skill.  Timing is converted
tick -> seconds (piecewise tempo map) -> beats (document tempo) in this module
only.
"""

from __future__ import annotations

import io
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from app.core.errors import UnsupportedMediaError, ValidationAppError
from app.core.logging import get_logger
from app.schemas.keyboard import KeyboardLayout
from app.schemas.music_document import (
    MusicDocument,
    MusicTrack,
    SourceMetadata,
    TimeSignature,
    new_id,
)
from app.services.music_document.engine import reindex

logger = get_logger("pocketscore.midi")

DEFAULT_TEMPO = 120.0
DEFAULT_MICROSECONDS_PER_BEAT = 500_000  # 120 BPM
MAX_TRACKS = 24
MAX_EVENTS = 20_000
DRUM_CHANNEL = 9


@dataclass
class ParsedNote:
    pitch: int
    start_seconds: float
    duration_seconds: float
    velocity: int
    channel: int
    track_index: int


@dataclass
class MidiParseResult:
    notes: List[ParsedNote] = field(default_factory=list)
    tempo: float = DEFAULT_TEMPO
    time_signature: TimeSignature = field(default_factory=TimeSignature)
    track_names: Dict[int, str] = field(default_factory=dict)
    channels: List[int] = field(default_factory=list)
    duration_seconds: float = 0.0
    ticks_per_beat: int = 480
    midi_format: int = 1
    warnings: List[str] = field(default_factory=list)


def _require_mido():
    try:
        import mido
    except ImportError as exc:  # pragma: no cover - dependency is installed
        raise UnsupportedMediaError(
            "MIDI support requires the 'mido' package", code="MIDI_BACKEND_MISSING"
        ) from exc
    return mido


def repair_text(value: str) -> str:
    """Undo the classic UTF-8-read-as-latin-1 mojibake in meta text.

    mido decodes meta strings with latin-1 by default.  If the bytes were
    actually UTF-8, re-encoding and decoding restores the original text.  Text
    that is genuinely latin-1 (e.g. ``Müller``) fails the UTF-8 decode and is
    returned unchanged.
    """
    if not value:
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _build_tempo_map(midi) -> List[Tuple[int, int]]:
    """Sorted ``(absolute_tick, microseconds_per_beat)`` map with a tick-0 entry."""
    raw: List[Tuple[int, int]] = []
    for track in midi.tracks:
        absolute = 0
        for msg in track:
            absolute += msg.time
            if msg.type == "set_tempo":
                raw.append((absolute, int(msg.tempo)))
    raw.sort(key=lambda item: item[0])
    if not raw or raw[0][0] != 0:
        raw.insert(0, (0, DEFAULT_MICROSECONDS_PER_BEAT))
    deduped: List[Tuple[int, int]] = []
    for tick, tempo in raw:
        if deduped and deduped[-1][0] == tick:
            deduped[-1] = (tick, tempo)
        else:
            deduped.append((tick, tempo))
    return deduped


def _ticks_to_seconds(ticks: int, tempo_map: List[Tuple[int, int]], ticks_per_beat: int) -> float:
    seconds = 0.0
    for index, (segment_tick, microseconds) in enumerate(tempo_map):
        seconds_per_tick = (microseconds / 1_000_000.0) / ticks_per_beat
        next_tick = tempo_map[index + 1][0] if index + 1 < len(tempo_map) else None
        if ticks <= segment_tick:
            return seconds
        if next_tick is None:
            return seconds + (ticks - segment_tick) * seconds_per_tick
        if ticks <= next_tick:
            return seconds + (ticks - segment_tick) * seconds_per_tick
        seconds += (next_tick - segment_tick) * seconds_per_tick
    return seconds


def parse_midi(data: bytes) -> MidiParseResult:
    """Parse raw MIDI bytes into notes on a seconds timeline."""
    mido = _require_mido()
    try:
        midi = mido.MidiFile(file=io.BytesIO(data))
    except Exception as exc:
        raise ValidationAppError(
            "the uploaded file is not a valid MIDI file",
            code="MIDI_PARSE_ERROR",
            details={"reason": str(exc)},
        ) from exc

    ticks_per_beat = int(getattr(midi, "ticks_per_beat", 480)) or 480
    result = MidiParseResult(
        ticks_per_beat=ticks_per_beat,
        midi_format=int(getattr(midi, "type", 1)),
    )
    tempo_map = _build_tempo_map(midi)
    result.tempo = round(60_000_000.0 / tempo_map[0][1], 2)
    if len({tempo for _tick, tempo in tempo_map}) > 1:
        result.warnings.append(
            f"检测到 {len({tempo for _tick, tempo in tempo_map})} 个速度变化点，"
            f"导入以 {result.tempo} BPM 作为文档速度，时间轴按真实速度换算"
        )

    time_signatures: List[Tuple[int, int]] = []

    for track_index, track in enumerate(midi.tracks):
        if track_index >= MAX_TRACKS:
            result.warnings.append(f"仅导入前 {MAX_TRACKS} 条轨道，其余被忽略")
            break
        pending: Dict[Tuple[int, int], Deque[Tuple[int, int]]] = defaultdict(deque)
        absolute_tick = 0
        skipped_drums = False
        for msg in track:
            absolute_tick += msg.time
            if msg.type == "time_signature":
                time_signatures.append((msg.numerator, msg.denominator))
            elif msg.type == "track_name" and track_index not in result.track_names:
                result.track_names[track_index] = repair_text(str(msg.name))
            elif msg.type == "note_on" and msg.velocity > 0:
                if msg.channel == DRUM_CHANNEL:
                    skipped_drums = True
                    continue
                pending[(msg.channel, msg.note)].append((absolute_tick, int(msg.velocity)))
                if msg.channel not in result.channels:
                    result.channels.append(msg.channel)
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                queue = pending.get((msg.channel, msg.note))
                if not queue:
                    continue
                start_tick, velocity = queue.popleft()
                result.notes.append(
                    _make_note(
                        pitch=int(msg.note),
                        start_tick=start_tick,
                        end_tick=absolute_tick,
                        velocity=velocity,
                        channel=int(msg.channel),
                        track_index=track_index,
                        tempo_map=tempo_map,
                        ticks_per_beat=ticks_per_beat,
                    )
                )
        if skipped_drums:
            result.warnings.append("已跳过打击乐通道（channel 10 / 索引 9）")

        # Notes without a matching note_off are closed at the end of the track.
        trailing = [item for queue in pending.values() for item in queue]
        if trailing:
            result.warnings.append("检测到未闭合的 note_on，已按轨道末尾补齐时值")
            for (channel, note), queue in pending.items():
                while queue:
                    start_tick, velocity = queue.popleft()
                    result.notes.append(
                        _make_note(
                            pitch=note,
                            start_tick=start_tick,
                            end_tick=max(absolute_tick, start_tick + 1),
                            velocity=velocity,
                            channel=channel,
                            track_index=track_index,
                            tempo_map=tempo_map,
                            ticks_per_beat=ticks_per_beat,
                        )
                    )

    if not result.notes:
        raise ValidationAppError(
            "the MIDI file does not contain any notes", code="MIDI_EMPTY"
        )

    if time_signatures:
        used = {tuple(ts) for ts in time_signatures}
        numerator, denominator = time_signatures[0]
        result.time_signature = (
            TimeSignature() if (numerator, denominator) == (4, 4)
            else TimeSignature(numerator=numerator, denominator=denominator)
        )
        if len(used) > 1:
            result.warnings.append(f"检测到 {len(used)} 种拍号，导入仅使用首个拍号")

    result.notes.sort(key=lambda n: (n.start_seconds, n.track_index, n.pitch))
    if len(result.notes) > MAX_EVENTS:
        result.warnings.append(f"音符数超过 {MAX_EVENTS}，仅保留最早的部分")
        result.notes = result.notes[:MAX_EVENTS]
    result.duration_seconds = max(n.start_seconds + n.duration_seconds for n in result.notes)
    return result


def _make_note(
    *,
    pitch: int,
    start_tick: int,
    end_tick: int,
    velocity: int,
    channel: int,
    track_index: int,
    tempo_map: List[Tuple[int, int]],
    ticks_per_beat: int,
) -> ParsedNote:
    start_seconds = _ticks_to_seconds(start_tick, tempo_map, ticks_per_beat)
    end_seconds = _ticks_to_seconds(end_tick, tempo_map, ticks_per_beat)
    duration = max(end_seconds - start_seconds, 0.01)
    return ParsedNote(
        pitch=pitch,
        start_seconds=start_seconds,
        duration_seconds=duration,
        velocity=max(1, min(127, velocity)),
        channel=channel,
        track_index=track_index,
    )


def parse_result_to_document(
    parsed: MidiParseResult,
    *,
    title: str,
    artist: str = "未知艺人",
    filename: Optional[str] = None,
    keyboard_layout: Optional[KeyboardLayout] = None,
) -> MusicDocument:
    """Convert a parse result into a validated MusicDocument."""
    from app.schemas.keyboard import DEFAULT_LAYOUT_ID, default_layout

    tempo = parsed.tempo if 20.0 <= parsed.tempo <= 400.0 else DEFAULT_TEMPO
    seconds_to_beats = tempo / 60.0

    used_tracks = sorted({note.track_index for note in parsed.notes})
    track_id_by_index: Dict[int, str] = {}
    tracks: List[MusicTrack] = []
    for position, track_index in enumerate(used_tracks):
        track_id = f"t{position + 1}"
        track_id_by_index[track_index] = track_id
        name = parsed.track_names.get(track_index) or f"轨道 {track_index + 1}"
        channel = next((n.channel for n in parsed.notes if n.track_index == track_index), None)
        tracks.append(
            MusicTrack(
                track_id=track_id,
                name=name[:80],
                instrument="piano",
                channel=channel,
                index=position,
                color=_track_color(position),
            )
        )

    events_payload = []
    for note in parsed.notes:
        events_payload.append(
            {
                "event_id": new_id(),
                "pitch": note.pitch,
                "start_time": round(note.start_seconds * seconds_to_beats, 6),
                "duration": round(max(note.duration_seconds * seconds_to_beats, 1 / 64), 6),
                "velocity": note.velocity,
                "track_id": track_id_by_index[note.track_index],
                "kind": "note",
            }
        )

    document = MusicDocument(
        title=(title[:200] or "未命名谱面"),
        artist=artist[:200],
        tempo=float(tempo),
        time_signature=parsed.time_signature,
        tracks=tracks,
        events=events_payload,
        keyboard_layout=keyboard_layout or default_layout(DEFAULT_LAYOUT_ID),
        source_metadata=SourceMetadata(kind="midi", filename=filename),
    )
    reindex(document)
    return document


def _track_color(index: int) -> str:
    palette = ["#3ddc97", "#22d3ee", "#8b5cf6", "#f5a524", "#fb7185", "#38bdf8", "#a3e635"]
    return palette[index % len(palette)]


def inspect_midi(data: bytes) -> Dict:
    """Lightweight metadata for the import preview UI."""
    parsed = parse_midi(data)
    return {
        "tempo": parsed.tempo,
        "time_signature": f"{parsed.time_signature.numerator}/{parsed.time_signature.denominator}",
        "ticks_per_beat": parsed.ticks_per_beat,
        "midi_format": parsed.midi_format,
        "tracks": len({n.track_index for n in parsed.notes}),
        "channels": parsed.channels,
        "notes": len(parsed.notes),
        "duration_seconds": round(parsed.duration_seconds, 4),
        "pitch_range": [min(n.pitch for n in parsed.notes), max(n.pitch for n in parsed.notes)],
        "track_names": {str(k): v for k, v in parsed.track_names.items()},
        "warnings": parsed.warnings,
    }


def import_midi_bytes(
    data: bytes,
    *,
    title: str,
    artist: str = "未知艺人",
    filename: Optional[str] = None,
    keyboard_layout: Optional[KeyboardLayout] = None,
) -> MusicDocument:
    return parse_result_to_document(
        parse_midi(data),
        title=title,
        artist=artist,
        filename=filename,
        keyboard_layout=keyboard_layout,
    )
