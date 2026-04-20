"""Latency benchmark for the Parakeet dictation pipeline.

Runs a folder of 16 kHz mono WAV files through ``SileroVad`` + ``ParakeetAsr`` +
``FixupEngine`` (the same stages the daemon executes between mic-stop and
clipboard-write) and reports per-stage and end-to-end timings.

Handover §9b target: <500 ms end-to-end for a 15 s prompt on RTX 5080.

Usage
-----
::

    python scripts/bench.py --wav-dir ./samples --runs 5
    python scripts/bench.py --wav-dir ./samples --no-vad
    python scripts/bench.py --wav-dir ./samples --config alt.toml

The WAV files must be 16 kHz, mono, 16-bit PCM — what the daemon records. A
helpful error is raised for other formats; convert with ``ffmpeg -ar 16000 -ac 1
-sample_fmt s16`` or similar if needed.

Mic capture and the paste stage are intentionally excluded: mic timing is bound
to real-time audio length, and paste depends on the target window. This matches
the handover's "audio end → clipboard write" framing (the interesting work).
"""

from __future__ import annotations

import argparse
import logging
import statistics
import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

# Make ``src/`` importable when running the script directly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from parakeet_dictation.asr import ParakeetAsr  # noqa: E402
from parakeet_dictation.config import load_config  # noqa: E402
from parakeet_dictation.fixups import FixupEngine  # noqa: E402
from parakeet_dictation.vad import SileroVad  # noqa: E402

log = logging.getLogger("bench")


class WavFormatError(RuntimeError):
    """Raised when a WAV file isn't 16 kHz / mono / 16-bit PCM."""


@dataclass
class StageTimings:
    vad_ms: float = 0.0
    asr_ms: float = 0.0
    fixup_ms: float = 0.0

    @property
    def total_ms(self) -> float:
        return self.vad_ms + self.asr_ms + self.fixup_ms


@dataclass
class FileResult:
    path: Path
    duration_s: float
    transcript: str
    runs: list[StageTimings] = field(default_factory=list)

    def total_ms_list(self) -> list[float]:
        return [r.total_ms for r in self.runs]


def load_wav_pcm16(path: Path) -> tuple[bytes, float]:
    """Return (PCM16 bytes, duration in seconds) for a 16 kHz mono WAV."""
    with wave.open(str(path), "rb") as wf:
        if wf.getnchannels() != 1:
            raise WavFormatError(f"{path}: expected mono, got {wf.getnchannels()} channels")
        if wf.getframerate() != 16000:
            raise WavFormatError(
                f"{path}: expected 16000 Hz, got {wf.getframerate()} Hz"
            )
        if wf.getsampwidth() != 2:
            raise WavFormatError(
                f"{path}: expected 16-bit PCM, got {wf.getsampwidth() * 8}-bit"
            )
        frames = wf.getnframes()
        audio = wf.readframes(frames)
    duration = frames / 16000.0
    return audio, duration


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. ``pct`` is 0–100."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round(pct / 100.0 * (len(ordered) - 1)))))
    return ordered[k]


def _time_stage() -> float:
    return time.perf_counter()


def _bench_one(
    audio: bytes,
    vad: SileroVad | None,
    asr: ParakeetAsr,
    fixups: FixupEngine | None,
) -> tuple[StageTimings, str]:
    t = StageTimings()
    t0 = _time_stage()
    trimmed = vad.trim(audio) if vad is not None else audio
    t1 = _time_stage()
    raw = asr.transcribe(trimmed) if trimmed else ""
    t2 = _time_stage()
    final = fixups.apply(raw) if fixups is not None else raw
    t3 = _time_stage()

    t.vad_ms = (t1 - t0) * 1000
    t.asr_ms = (t2 - t1) * 1000
    t.fixup_ms = (t3 - t2) * 1000
    return t, final


def _format_summary(results: list[FileResult]) -> str:
    all_totals: list[float] = []
    for r in results:
        all_totals.extend(r.total_ms_list())

    lines: list[str] = []
    lines.append("")
    lines.append(
        f"{'file':<30} {'dur':>6} {'runs':>4} "
        f"{'vad p50':>8} {'asr p50':>8} {'fix p50':>8} {'e2e p50':>8} {'e2e p95':>8}"
    )
    lines.append("-" * 92)
    for r in results:
        vads = [run.vad_ms for run in r.runs]
        asrs = [run.asr_ms for run in r.runs]
        fxs = [run.fixup_ms for run in r.runs]
        totals = r.total_ms_list()
        name = r.path.name
        if len(name) > 29:
            name = name[:26] + "..."
        lines.append(
            f"{name:<30} {r.duration_s:>5.1f}s {len(r.runs):>4} "
            f"{percentile(vads, 50):>7.0f}ms {percentile(asrs, 50):>7.0f}ms "
            f"{percentile(fxs, 50):>7.1f}ms {percentile(totals, 50):>7.0f}ms "
            f"{percentile(totals, 95):>7.0f}ms"
        )

    lines.append("")
    lines.append("Aggregate end-to-end (all files × all runs):")
    if all_totals:
        lines.append(f"  samples : {len(all_totals)}")
        lines.append(f"  mean    : {statistics.fmean(all_totals):.0f} ms")
        lines.append(f"  p50     : {percentile(all_totals, 50):.0f} ms")
        lines.append(f"  p95     : {percentile(all_totals, 95):.0f} ms")
        lines.append(f"  p99     : {percentile(all_totals, 99):.0f} ms")
        lines.append(f"  max     : {max(all_totals):.0f} ms")
        lines.append("")
        target = 500.0
        lines.append(f"Handover §9b target: <{target:.0f} ms end-to-end for a 15 s prompt.")
        for r in results:
            if 10 <= r.duration_s <= 20:
                p95 = percentile(r.total_ms_list(), 95)
                verdict = "OK" if p95 < target else "OVER"
                lines.append(f"  {r.path.name}: {r.duration_s:.1f}s -> p95 {p95:.0f} ms [{verdict}]")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="bench",
        description="Latency benchmark for the parakeet-dictation pipeline.",
    )
    parser.add_argument(
        "--wav-dir",
        type=Path,
        required=True,
        help="Directory of 16 kHz mono 16-bit WAV files to benchmark against.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="How many times to re-run each WAV (default: 3). First run is always kept; "
        "set to 1 to measure cold-path behaviour.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="config.toml path (default: ./config.toml).",
    )
    parser.add_argument(
        "--fixups",
        type=Path,
        default=Path("vocab_fixups.json"),
        help="vocab_fixups.json path (default: ./vocab_fixups.json).",
    )
    parser.add_argument(
        "--no-vad",
        action="store_true",
        help="Skip Silero VAD — send the raw WAV straight to the encoder.",
    )
    parser.add_argument(
        "--no-fixups",
        action="store_true",
        help="Skip vocab fixups — report raw Parakeet output.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Debug-level logging.",
    )
    args = parser.parse_args()

    # Windows console defaults to cp1252 which chokes on e.g. Swedish letters
    # in Parakeet's transcripts. Reconfigure to UTF-8 so logging / summary can't
    # crash on non-ASCII output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    if not args.wav_dir.is_dir():
        print(f"WAV dir not found: {args.wav_dir}", file=sys.stderr)
        return 2

    wavs = sorted(args.wav_dir.glob("*.wav"))
    if not wavs:
        print(f"No *.wav files in {args.wav_dir}", file=sys.stderr)
        return 2

    config = load_config(args.config)
    vad = None if args.no_vad else SileroVad(config.vad)
    asr = ParakeetAsr(config.asr)
    asr.load()
    asr.warmup()
    if vad is not None:
        vad.warmup()
    fixups = None if args.no_fixups else FixupEngine(args.fixups)

    log.info("Benchmarking %d WAV file(s) × %d run(s) each", len(wavs), args.runs)

    results: list[FileResult] = []
    for wav_path in wavs:
        try:
            audio, duration = load_wav_pcm16(wav_path)
        except WavFormatError as exc:
            log.warning("Skipping %s: %s", wav_path.name, exc)
            continue
        except wave.Error as exc:
            log.warning("Could not read %s: %s", wav_path.name, exc)
            continue

        result = FileResult(path=wav_path, duration_s=duration, transcript="")
        for run_idx in range(args.runs):
            timings, text = _bench_one(audio, vad, asr, fixups)
            result.runs.append(timings)
            if run_idx == 0:
                result.transcript = text
                log.info(
                    "%s (%.1fs) -> %.0f ms [vad=%.0f asr=%.0f fix=%.1f] %r",
                    wav_path.name,
                    duration,
                    timings.total_ms,
                    timings.vad_ms,
                    timings.asr_ms,
                    timings.fixup_ms,
                    text[:80],
                )
            else:
                log.debug(
                    "%s run %d: %.0f ms", wav_path.name, run_idx + 1, timings.total_ms
                )
        results.append(result)

    if not results:
        print("No benchmarkable files", file=sys.stderr)
        return 2

    print(_format_summary(results))
    asr.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
