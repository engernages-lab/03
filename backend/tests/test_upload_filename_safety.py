"""Upload filename sanitisation tests (V1.1-C.2.3.4.2)."""

from __future__ import annotations

import pytest

from app.core.paths import (
    MAX_FILENAME_LENGTH,
    sanitize_extension,
    sanitize_upload_filename,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("song.wav", "song.wav"),
        ("My Song.mp3", "My Song.mp3"),
        ("../../escape.wav", "escape.wav"),
        (r"..\..\escape.wav", "escape.wav"),
        ("/etc/passwd", "passwd"),
        (r"C:\temp\song.wav", "song.wav"),
        (r"\\server\share\song.wav", "song.wav"),
        ("中文歌曲.wav", "中文歌曲.wav"),
        ("日本語の曲.mp3", "日本語の曲.mp3"),
        ("  spaced name .wav ", "spaced name.wav"),
    ],
)
def test_common_names_are_sanitised(raw: str, expected: str) -> None:
    assert sanitize_upload_filename(raw) == expected


def test_path_separators_never_survive() -> None:
    for raw in ("a/b/c.wav", r"a\b\c.wav", "../../x.wav", r"C:\Windows\x.wav"):
        cleaned = sanitize_upload_filename(raw)
        assert "/" not in cleaned and "\\" not in cleaned


def test_control_characters_are_stripped() -> None:
    cleaned = sanitize_upload_filename("bad\x01name\x1f.wav")
    assert all(ord(ch) >= 32 for ch in cleaned)
    assert cleaned.endswith(".wav")


def test_nul_byte_is_removed() -> None:
    assert "\x00" not in sanitize_upload_filename("evil\x00.wav")


def test_empty_and_dot_names_fall_back() -> None:
    assert sanitize_upload_filename("") == "audio"
    assert sanitize_upload_filename("   ") == "audio"
    assert sanitize_upload_filename("...") == "audio"
    assert sanitize_upload_filename(None) == "audio"
    assert sanitize_upload_filename("", fallback="upload.bin") == "upload.bin"


def test_long_names_are_truncated_but_keep_extension() -> None:
    cleaned = sanitize_upload_filename("n" * 400 + ".wav")
    assert len(cleaned) <= MAX_FILENAME_LENGTH + 5
    assert cleaned.endswith(".wav")


def test_windows_reserved_names_are_neutralised() -> None:
    cleaned = sanitize_upload_filename("CON.wav")
    assert cleaned.split(".")[0].upper() != "CON"
    assert cleaned.endswith(".wav")


def test_double_extension_is_preserved_so_the_validator_can_reject_it() -> None:
    cleaned = sanitize_upload_filename("song.wav.exe")
    assert sanitize_extension(cleaned) == ".exe"


@pytest.mark.parametrize("exploit", ["../../x.wav", r"..\..\x.wav", "/etc/passwd", "C:\\x.wav", "\\\\h\\s\\x"])
def test_extension_extraction_survives_hostile_input(exploit: str) -> None:
    assert sanitize_extension(exploit) in {".wav", ""}


@pytest.mark.parametrize(
    "extension",
    [".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus"],
)
def test_supported_extensions_are_preserved(extension: str) -> None:
    cleaned = sanitize_upload_filename(f"track{extension}")
    assert cleaned == f"track{extension}"
    assert sanitize_extension(cleaned) == extension


def test_odd_extensions_are_rejected_by_the_extractor() -> None:
    for raw in ("no-extension", "x." + "y" * 12, ".hidden"):
        assert sanitize_extension(raw) in {"", ".hidden".lstrip(".")} or sanitize_extension(raw) == ""


def test_right_to_left_override_is_removed() -> None:
    # U+202E can make a filename render as a different extension in a file manager
    assert "\u202e" not in sanitize_upload_filename("song\u202eexe.wav")
