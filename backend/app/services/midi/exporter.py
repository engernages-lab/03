"""MIDI export (MusicDocument -> .mid) using mido."""

from __future__ import annotations

import io

from app.core.errors import DependencyMissingError
from app.schemas.music_document import MusicDocument

TICKS_PER_BEAT = 480

try:  # mido >= 1.2 accepts a charset keyword on MidiFile
    import mido as _mido_probe

    _SUPPORTS_UTF8 = "charset" in __import__("inspect").signature(_mido_probe.MidiFile).parameters
except Exception:  # pragma: no cover - defensive
    _SUPPORTS_UTF8 = False


def _prepare_charset() -> bool:
    """mido saves meta text with ``MidiFile.charset`` (default latin-1).

    We attempt UTF-8 so CJK titles survive; callers fall back to an ASCII-safe
    name when the installed mido does not accept the parameter.
    """
    return _SUPPORTS_UTF8


def _safe_name(name: str, utf8_ok: bool) -> str:
    if utf8_ok:
        return name
    return name.encode("ascii", "replace").decode("ascii")


def _new_midi_file(mido, utf8_ok: bool):
    kwargs = {"type": 1, "ticks_per_beat": TICKS_PER_BEAT}
    if utf8_ok:
        try:
            return mido.MidiFile(charset="utf-8", **kwargs)
        except TypeError:  # pragma: no cover - very old mido
            pass
    return mido.MidiFile(**kwargs)


def document_to_midi_bytes(document: MusicDocument) -> bytes:
    try:
        import mido
    except ImportError as exc:  # pragma: no cover - dependency installed
        raise DependencyMissingError("mido is required for MIDI export") from exc

    utf8_ok = _prepare_charset()
    midi = _new_midi_file(mido, utf8_ok)
    meta = mido.MidiTrack()
    midi.tracks.append(meta)
    meta.append(mido.MetaMessage("track_name", name=_safe_name(document.title[:120], utf8_ok), time=0))
    meta.append(
        mido.MetaMessage(
            "time_signature",
            numerator=document.time_signature.numerator,
            denominator=document.time_signature.denominator,
            time=0,
        )
    )
    microseconds = int(round(60_000_000 / document.tempo))
    meta.append(mido.MetaMessage("set_tempo", tempo=microseconds, time=0))

    for track in document.tracks:
        events = [e for e in document.events if e.track_id == track.track_id]
        if not events:
            continue
        midi_track = mido.MidiTrack()
        midi.tracks.append(midi_track)
        midi_track.append(mido.MetaMessage("track_name", name=_safe_name(track.name[:120], utf8_ok), time=0))
        channel = track.channel if track.channel is not None else min(track.index, 15)

        # (tick, order, message); note_off before note_on at the same tick keeps
        # repeated pitches from cancelling each other out.
        scheduled = []
        for event in events:
            if event.pitch is None:
                continue
            start_tick = int(round(event.start_time * TICKS_PER_BEAT))
            end_tick = int(round(event.end_time * TICKS_PER_BEAT))
            if end_tick <= start_tick:
                end_tick = start_tick + 1
            scheduled.append(
                (start_tick, 1, mido.Message("note_on", note=event.pitch, velocity=event.velocity, channel=channel))
            )
            scheduled.append(
                (end_tick, 0, mido.Message("note_off", note=event.pitch, velocity=0, channel=channel))
            )
        scheduled.sort(key=lambda item: (item[0], item[1]))

        previous_tick = 0
        for tick, _order, message in scheduled:
            message.time = max(0, tick - previous_tick)
            previous_tick = tick
            midi_track.append(message)

    buffer = io.BytesIO()
    midi.save(file=buffer)
    return buffer.getvalue()
