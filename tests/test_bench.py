"""Tests for ``scripts/bench.py`` helpers that don't require model loading."""

from __future__ import annotations

import importlib.util
import math
import sys
import wave
from pathlib import Path

import numpy as np
import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_BENCH_PATH = _REPO_ROOT / "scripts" / "bench.py"


@pytest.fixture(scope="module")
def bench_module():
    """Load ``scripts/bench.py`` as a module without executing its CLI."""
    spec = importlib.util.spec_from_file_location("bench_under_test", _BENCH_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench_under_test"] = module
    spec.loader.exec_module(module)
    return module


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int, channels: int, sampwidth: int) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())


def test_load_wav_pcm16_roundtrip(bench_module, tmp_path: Path) -> None:
    sr = 16000
    tone = (np.sin(2 * np.pi * 440 * np.arange(sr) / sr) * 0.1 * 32767).astype(np.int16)
    wav = tmp_path / "tone.wav"
    _write_wav(wav, tone, sample_rate=sr, channels=1, sampwidth=2)

    audio, duration = bench_module.load_wav_pcm16(wav)

    assert len(audio) == tone.nbytes
    assert duration == pytest.approx(1.0, rel=1e-3)


def test_load_wav_rejects_stereo(bench_module, tmp_path: Path) -> None:
    samples = np.zeros((1600, 2), dtype=np.int16)
    wav = tmp_path / "stereo.wav"
    _write_wav(wav, samples, sample_rate=16000, channels=2, sampwidth=2)
    with pytest.raises(bench_module.WavFormatError, match="mono"):
        bench_module.load_wav_pcm16(wav)


def test_load_wav_rejects_wrong_sample_rate(bench_module, tmp_path: Path) -> None:
    samples = np.zeros(1600, dtype=np.int16)
    wav = tmp_path / "48k.wav"
    _write_wav(wav, samples, sample_rate=48000, channels=1, sampwidth=2)
    with pytest.raises(bench_module.WavFormatError, match="16000 Hz"):
        bench_module.load_wav_pcm16(wav)


def test_load_wav_rejects_wrong_bit_depth(bench_module, tmp_path: Path) -> None:
    samples = np.zeros(1600, dtype=np.int32)
    wav = tmp_path / "32bit.wav"
    _write_wav(wav, samples, sample_rate=16000, channels=1, sampwidth=4)
    with pytest.raises(bench_module.WavFormatError, match="16-bit"):
        bench_module.load_wav_pcm16(wav)


def test_percentile_empty(bench_module) -> None:
    assert math.isnan(bench_module.percentile([], 50))


def test_percentile_nearest_rank(bench_module) -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert bench_module.percentile(values, 0) == 10.0
    assert bench_module.percentile(values, 50) == 30.0
    assert bench_module.percentile(values, 100) == 50.0


def test_stage_timings_total(bench_module) -> None:
    t = bench_module.StageTimings(vad_ms=5.0, asr_ms=250.0, fixup_ms=0.2)
    assert t.total_ms == pytest.approx(255.2)


def test_file_result_totals(bench_module, tmp_path: Path) -> None:
    runs = [
        bench_module.StageTimings(vad_ms=5, asr_ms=250, fixup_ms=1),
        bench_module.StageTimings(vad_ms=6, asr_ms=260, fixup_ms=2),
    ]
    result = bench_module.FileResult(path=tmp_path / "x.wav", duration_s=2.0, transcript="", runs=runs)
    assert result.total_ms_list() == [256, 268]
