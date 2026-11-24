"""Key-signature parsing shared by the notation engines.

Owner: pocket-jianpu-notation skill.  This maps a key label such as ``F#m`` to
a tonic pitch class and mode so that scale degrees can be derived.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from app.core.errors import ValidationAppError

NOTE_TO_PC: Dict[str, int] = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
NATURAL_MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)

DEGREE_LABELS = ("1", "2", "3", "4", "5", "6", "7")
SOLFEGE_LABELS = ("do", "re", "mi", "fa", "sol", "la", "si")


@dataclass(frozen=True)
class KeyContext:
    label: str
    tonic_pc: int
    mode: str  # "major" | "minor"
    scale: Tuple[int, ...]

    @property
    def is_minor(self) -> bool:
        return self.mode == "minor"


def parse_key_signature(key_signature: str) -> KeyContext:
    raw = (key_signature or "C").strip()
    mode = "major"
    tonic_text = raw
    # Minor labels always end with a lower-case "m" (Am, F#m, Bbm); "Bb" ends with
    # "b" so it stays major.
    if raw.endswith("m"):
        mode = "minor"
        tonic_text = raw[:-1]
    if tonic_text not in NOTE_TO_PC:
        raise ValidationAppError(
            f"unsupported key signature {key_signature!r}",
            code="UNSUPPORTED_KEY_SIGNATURE",
            details={"received": key_signature},
        )
    return KeyContext(
        label=raw,
        tonic_pc=NOTE_TO_PC[tonic_text],
        mode=mode,
        scale=NATURAL_MINOR_SCALE if mode == "minor" else MAJOR_SCALE,
    )


def degree_for_pitch(pitch: int, key: KeyContext, prefer_flat: bool = False) -> Tuple[int, str | None, int]:
    """Map a MIDI pitch to ``(degree, accidental, octave_offset)``.

    ``degree`` is 1-7, ``accidental`` is ``"#"``/``"b"``/``None`` and
    ``octave_offset`` is relative to the middle octave, which is the octave of
    the tonic nearest to C4 (e.g. G4 for G major, A4 for A minor).  Positive
    offsets render as dots above, negative as dots below.

    Chromatic notes sit one semitone from two different degrees; ``prefer_flat``
    chooses which spelling wins (sharp by default).
    """
    delta = pitch - key.tonic_pc
    relative = delta % 12
    # Middle octave reference: the tonic within C4..B4.
    tonic_reference = 60 + key.tonic_pc
    octave = (pitch - tonic_reference) // 12

    if relative in key.scale:
        degree = key.scale.index(relative) + 1
        return degree, None, octave

    # Nearest scale degree with a single accidental.  On a tie the spelling
    # depends on ``prefer_flat``: sharps are the default because raised notes
    # (#4, #5) are the common case in instructional jianpu.
    best_degree = 1
    best_diff = 12
    for index, semitone in enumerate(key.scale):
        diff = relative - semitone
        if diff > 6:
            diff -= 12
        elif diff < -6:
            diff += 12
        if abs(diff) < abs(best_diff) or (
            abs(diff) == abs(best_diff)
            and ((prefer_flat and diff < 0 < best_diff) or (not prefer_flat and diff > 0 > best_diff))
        ):
            best_degree = index + 1
            best_diff = diff
    accidental = "#" if best_diff > 0 else "b"
    return best_degree, accidental, octave


def degree_label(degree: int, accidental: str | None) -> str:
    token = DEGREE_LABELS[max(0, min(6, degree - 1))]
    if accidental:
        return f"{accidental}{token}"
    return token


def solfege_label(degree: int) -> str:
    return SOLFEGE_LABELS[max(0, min(6, degree - 1))]


def scale_pitches(key: KeyContext, low: int = 48, high: int = 84) -> List[int]:
    """All in-scale MIDI pitches within a range (used for tests/utilities)."""
    return [p for p in range(low, high + 1) if (p - key.tonic_pc) % 12 in key.scale]
