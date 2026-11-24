"""MIDI import tests built from synthesised .mid files (no fixtures on disk)."""

from __future__ import annotations

import io

import pytest

from app.core.errors import ValidationAppError
from app.services.midi.exporter import document_to_midi_bytes
from app.services.midi.importer import (
    import_midi_bytes,
    inspect_midi,
    parse_midi,
    parse_result_to_document,
)
from app.schemas.music_document import empty_document
from app.services import music_document as core


def build_midi_bytes(
    notes,
    *,
    tempo_bpm: float = 120.0,
    time_signature=(4, 4),
    ticks_per_beat: int = 480,
    track_names=None,
    channels=None,
) -> bytes:
    """Create a real MIDI file with mido from ``notes`` tuples.

    ``notes`` items: (pitch, start_beats, duration_beats, velocity)
    """
    import mido

    midi = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat, charset="utf-8")
    meta = mido.MidiTrack()
    midi.tracks.append(meta)
    meta.append(mido.MetaMessage("set_tempo", tempo=int(60_000_000 / tempo_bpm), time=0))
    meta.append(
        mido.MetaMessage(
            "time_signature",
            numerator=time_signature[0],
            denominator=time_signature[1],
            time=0,
        )
    )

    grouped = {}
    for pitch, start, duration, velocity in notes:
        grouped.setdefault(0, []).append((pitch, start, duration, velocity))

    for track_index, track_notes in grouped.items():
        track = mido.MidiTrack()
        midi.tracks.append(track)
        name = (track_names or {}).get(track_index, f"Track {track_index + 1}")
        track.append(mido.MetaMessage("track_name", name=name, time=0))
        channel = (channels or {}).get(track_index, track_index)
        events = []
        for pitch, start, duration, velocity in track_notes:
            events.append((int(start * ticks_per_beat), 1, mido.Message("note_on", note=pitch, velocity=velocity, channel=channel)))
            events.append((int((start + duration) * ticks_per_beat), 0, mido.Message("note_off", note=pitch, velocity=0, channel=channel)))
        events.sort(key=lambda item: (item[0], item[1]))
        previous = 0
        for tick, _order, message in events:
            message.time = max(0, tick - previous)
            previous = tick
            track.append(message)

    buffer = io.BytesIO()
    midi.save(file=buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------

def test_parse_simple_melody():
    data = build_midi_bytes([(60, 0, 1, 90), (62, 1, 1, 80), (64, 2, 2, 70)])
    parsed = parse_midi(data)
    assert len(parsed.notes) == 3
    assert parsed.tempo == pytest.approx(120.0)
    assert parsed.time_signature.numerator == 4
    pitches = [n.pitch for n in parsed.notes]
    assert pitches == [60, 62, 64]
    # 2 beats @120bpm = 1.0s
    assert parsed.notes[2].duration_seconds == pytest.approx(1.0, abs=1e-3)


def test_parse_chord_is_grouped_by_start_time():
    data = build_midi_bytes([(60, 0, 2, 90), (64, 0, 2, 90), (67, 0, 2, 90)])
    parsed = parse_midi(data)
    assert len(parsed.notes) == 3
    starts = {round(n.start_seconds, 4) for n in parsed.notes}
    assert len(starts) == 1


def test_parse_respects_tempo_meta():
    data = build_midi_bytes([(60, 0, 1, 90)], tempo_bpm=60.0)
    parsed = parse_midi(data)
    assert parsed.tempo == pytest.approx(60.0)
    assert parsed.notes[0].duration_seconds == pytest.approx(1.0, abs=1e-3)


def test_parse_time_signature_and_ticks():
    data = build_midi_bytes([(60, 0, 1, 90)], time_signature=(3, 4), ticks_per_beat=960)
    parsed = parse_midi(data)
    assert (parsed.time_signature.numerator, parsed.time_signature.denominator) == (3, 4)
    assert parsed.ticks_per_beat == 960


def test_parse_overlapping_same_pitch_pairs_in_order():
    # Two C4 notes that overlap: 0..2 and 1..3
    data = build_midi_bytes([(60, 0, 2, 90), (60, 1, 2, 90)])
    parsed = parse_midi(data)
    assert len(parsed.notes) == 2
    durations = sorted(round(n.duration_seconds, 3) for n in parsed.notes)
    assert durations == [1.0, 1.0]


def test_invalid_midi_raises():
    with pytest.raises(ValidationAppError) as exc:
        parse_midi(b"this is not midi")
    assert exc.value.code == "MIDI_PARSE_ERROR"


def test_empty_midi_raises():
    import mido

    midi = mido.MidiFile()
    midi.tracks.append(mido.MidiTrack())
    buffer = io.BytesIO()
    midi.save(file=buffer)
    with pytest.raises(ValidationAppError) as exc:
        parse_midi(buffer.getvalue())
    assert exc.value.code == "MIDI_EMPTY"


def test_inspect_reports_metadata():
    data = build_midi_bytes([(48, 0, 1, 100), (72, 2, 1, 100)], tempo_bpm=90)
    info = inspect_midi(data)
    assert info["tempo"] == pytest.approx(90.0)
    assert info["notes"] == 2
    assert info["pitch_range"] == [48, 72]
    assert info["tracks"] >= 1
    assert info["time_signature"] == "4/4"


# ---------------------------------------------------------------------------
# document conversion
# ---------------------------------------------------------------------------

def test_document_from_midi_has_beats_and_keys():
    data = build_midi_bytes([(60, 0, 1, 90), (64, 1, 1, 90)])
    document = import_midi_bytes(data, title="MIDI 测试", filename="test.mid")
    assert document.title == "MIDI 测试"
    assert len(document.events) == 2
    assert document.source_metadata.kind == "midi"
    assert document.source_metadata.filename == "test.mid"
    first = document.events[0]
    assert first.start_time == pytest.approx(0.0, abs=1e-6)
    assert first.duration == pytest.approx(1.0, abs=1e-6)  # one beat at 120bpm
    assert first.mapped_key == "k0"
    assert first.measure == 1


def test_document_from_midi_creates_chords():
    data = build_midi_bytes([(60, 0, 1, 90), (64, 0, 1, 90), (67, 0, 1, 90)])
    document = import_midi_bytes(data, title="和弦")
    chord_ids = {e.chord_id for e in document.events}
    assert len(chord_ids) == 1
    assert None not in chord_ids


def test_document_from_midi_multiple_tracks():
    import mido

    midi = mido.MidiFile(type=1, ticks_per_beat=480, charset="utf-8")
    meta = mido.MidiTrack()
    midi.tracks.append(meta)
    meta.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))

    for index, pitch in enumerate((60, 48)):
        track = mido.MidiTrack()
        midi.tracks.append(track)
        track.append(mido.MetaMessage("track_name", name=f"声部{index + 1}", time=0))
        track.append(mido.Message("note_on", note=pitch, velocity=80, channel=index, time=0))
        track.append(mido.Message("note_off", note=pitch, velocity=0, channel=index, time=480))

    buffer = io.BytesIO()
    midi.save(file=buffer)
    document = import_midi_bytes(buffer.getvalue(), title="双轨")
    assert len(document.tracks) == 2
    assert {t.name for t in document.tracks} == {"声部1", "声部2"}
    assert {e.track_id for e in document.events} == {"t1", "t2"}


def test_document_duration_matches_midi():
    data = build_midi_bytes([(60, 0, 4, 90)])
    document = import_midi_bytes(data, title="时长")
    # 4 beats at 120bpm = 2 seconds
    assert document.duration == pytest.approx(2.0, abs=1e-3)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def test_export_roundtrip_preserves_notes():
    document = empty_document("导出测试", tempo=120)
    core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    core.add_event(document, pitch=64, start_time=1.0, duration=1.0)
    core.add_event(document, pitch=67, start_time=2.0, duration=2.0)

    payload = document_to_midi_bytes(document)
    parsed = parse_midi(payload)
    assert len(parsed.notes) == 3
    assert sorted(n.pitch for n in parsed.notes) == [60, 64, 67]
    assert parsed.tempo == pytest.approx(120.0)


def test_export_skips_rests():
    document = empty_document("含休止")
    core.add_event(document, pitch=60, start_time=0.0, duration=1.0)
    core.add_event(document, pitch=None, start_time=1.0, duration=1.0, kind="rest")
    parsed = parse_midi(document_to_midi_bytes(document))
    assert len(parsed.notes) == 1


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def test_api_inspect_and_import(client):
    data = build_midi_bytes([(60, 0, 1, 90), (62, 1, 1, 90)])
    response = client.post("/api/v1/midi/inspect", files={"file": ("demo.mid", data, "audio/midi")})
    assert response.status_code == 200, response.text
    assert response.json()["notes"] == 2

    response = client.post(
        "/api/v1/midi/import",
        files={"file": ("demo.mid", data, "audio/midi")},
        params={"title": "上传的 MIDI"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "上传的 MIDI"
    assert len(body["events"]) == 2
    assert body["document_id"]

    fetched = client.get(f"/api/v1/documents/{body['document_id']}")
    assert fetched.status_code == 200


def test_api_rejects_non_midi_extension(client):
    response = client.post(
        "/api/v1/midi/import", files={"file": ("song.mp3", b"audio", "audio/mpeg")}
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_api_export_downloads_midi(client):
    data = build_midi_bytes([(60, 0, 1, 90)])
    created = client.post(
        "/api/v1/midi/import", files={"file": ("demo.mid", data, "audio/midi")}
    ).json()
    response = client.get(f"/api/v1/midi/{created['document_id']}/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/midi")
    assert response.content[:4] == b"MThd"
