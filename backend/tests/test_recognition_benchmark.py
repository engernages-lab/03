"""Benchmark regression tests for V1.1-A recognition accuracy.

Each run really executes the model on synthesised audio with a MIDI ground
truth, so these are accuracy checks, not "did the model return something".

The thresholds encode the *achieved* V1.1-A quality (with a small margin), and
the task-book targets are asserted separately for the scenarios they name.
Thresholds live here, not in the corpus, so tuning cannot move the goalposts.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("basic_pitch", reason="audio transcription model not installed")

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "tests"))

from benchmark import corpus, metrics  # noqa: E402

from app.services.audio import note_extraction  # noqa: E402

pytestmark = pytest.mark.slow


@pytest.fixture(scope="session")
def corpus_root(tmp_path_factory):
    return tmp_path_factory.mktemp("recognition-corpus")


def _evaluate(cases, root):
    rows = []
    for case in cases:
        detected = note_extraction.transcribe_file(Path(case["wav"]))
        ends = [start + duration for _pitch, start, duration in case["bounds"]]
        score = metrics.score(
            [
                metrics.Detected(pitch=item.pitch, start=item.start, end=item.end, amplitude=item.amplitude)
                for item in detected
            ],
            case["reference"],
            duration=case["duration"],
            reference_ends=ends,
        )
        rows.append((case["category"], case["name"], score))
    return rows


def _aggregate(rows, category=None):
    selected = [score for name, _case, score in rows if category is None or name == category]
    return metrics.aggregate(selected)


@pytest.fixture(scope="session")
def dev_rows(corpus_root):
    cases = corpus.build_corpus(corpus_root / "dev", "dev")
    return _evaluate(cases, corpus_root)


@pytest.fixture(scope="session")
def test_rows(corpus_root):
    cases = corpus.build_corpus(corpus_root / "test", "test")
    return _evaluate(cases, corpus_root)


def test_every_case_has_a_midi_ground_truth(corpus_root):
    cases = corpus.build_corpus(corpus_root / "truth", "dev")
    for case in cases:
        midi = Path(case["midi"])
        assert midi.exists(), f"{case['name']} has no MIDI ground truth"
        assert midi.stat().st_size > 0
        data = midi.read_bytes()
        assert data[:4] == b"MThd", f"{case['name']} is not a MIDI file"


def test_dev_set_quality(dev_rows):
    overall = _aggregate(dev_rows)
    assert overall.precision >= 0.93
    assert overall.recall >= 0.95
    assert overall.f1 >= 0.95


def test_held_out_set_quality(test_rows):
    overall = _aggregate(test_rows)
    assert overall.precision >= 0.95
    assert overall.recall >= 0.90
    assert overall.f1 >= 0.95


def test_octave_and_fifth_chords_are_not_suppressed(dev_rows, test_rows):
    """Genuine octave/fifth intervals must survive the harmonic filter."""
    for rows in (dev_rows, test_rows):
        for category in ("octave_true", "fifth_true"):
            score = _aggregate(rows, category)
            assert score.true_positives == score.reference, category
            assert score.false_positives == 0, category


def test_triad_target_is_met(test_rows):
    """Task-book target: triad F1 >= 0.85."""
    score = _aggregate(test_rows, "triad")
    assert score.f1 >= 0.85, score.as_dict()


def test_fast_passage_target_is_met(test_rows):
    """Task-book target: 0.15 s notes, recall >= 0.70 and precision >= 0.85."""
    score = _aggregate(test_rows, "fast_015")
    assert score.recall >= 0.70, score.as_dict()
    assert score.precision >= 0.85, score.as_dict()


def test_single_voice_and_low_register_targets(test_rows):
    for category in ("monophonic", "low_register"):
        score = _aggregate(test_rows, category)
        assert score.f1 >= 0.95, (category, score.as_dict())


def test_repeated_pitch_is_split_not_merged(dev_rows):
    """TD-02: repeated notes used to collapse into one event."""
    score = _aggregate(dev_rows, "repeat_015")
    assert score.recall >= 0.75, score.as_dict()


def test_false_positive_rate_is_low(test_rows):
    overall = _aggregate(test_rows)
    assert overall.false_positive_rate <= 0.10, overall.as_dict()
    assert overall.false_positives_per_second <= 0.10


def test_pitch_accuracy_is_exact_for_matched_notes(dev_rows, test_rows):
    for rows in (dev_rows, test_rows):
        overall = _aggregate(rows)
        assert overall.pitch_accuracy >= 0.99


def test_onset_error_is_small(dev_rows, test_rows):
    for rows in (dev_rows, test_rows):
        overall = _aggregate(rows)
        assert overall.onset_mae <= 0.08  # seconds
