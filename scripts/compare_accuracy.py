"""Accuracy comparison harness — handover §9c.

Runs a directory of 16 kHz mono WAV files through up to three ASR pipelines and
writes their transcripts side-by-side into a markdown table, ready for manual
error-tagging.

Pipelines
---------
1. **Parakeet INT8 + fixups** (always; the daemon's default).
2. **Parakeet FP32 + fixups** (optional, ``--fp32-path <dir>``). Point at a
   second ``./models/parakeet-tdt-0.6b-v3-fp32`` folder containing the fp32
   ONNX files. If omitted, the column is skipped.
3. **Whisper large-v3 via faster-whisper** (optional, ``--whisper``). Requires
   ``pip install faster-whisper``; it is *not* a project dependency and is only
   imported when asked for.

Each WAV can optionally have a matching ``<name>.txt`` sidecar file containing
the reference transcript; it will be included in a ``reference`` column.

Usage
-----
::

    python scripts/compare_accuracy.py --wav-dir ./samples --out accuracy.md
    python scripts/compare_accuracy.py --wav-dir ./samples --out out.md \
        --fp32-path ./models/parakeet-tdt-0.6b-v3-fp32 --whisper

Notes
-----
* "Fixups" are applied uniformly to every column *except* the reference and
  Whisper columns (Whisper gets the same technical-vocabulary ``initial_prompt``
  from the handover §2b comparison instead, to keep the contest fair).
* Error tagging is manual; the script does not compute WER.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

# Make ``src/`` importable when running the script directly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from parakeet_dictation.config import load_config  # noqa: E402
from parakeet_dictation.fixups import FixupEngine  # noqa: E402

# Re-use the bench WAV loader.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench import WavFormatError, load_wav_pcm16  # noqa: E402

log = logging.getLogger("compare_accuracy")

# Technical vocabulary the user dictates regularly — used as Whisper's
# initial_prompt so the comparison is fair against Parakeet + fixups.
_WHISPER_INITIAL_PROMPT = (
    "Dependabot Gluetun qBittorrent pgvector Qdrant Synology Hestra Anonine "
    "Proton Gore-Tex DSM Claude Code Anthropic Garmin Ollama crates.io TOML "
    "CIDR JSON YAML NAS MCP RAG LLM VS Code Rust PowerShell"
)


@dataclass
class Sample:
    path: Path
    audio_pcm16: bytes
    duration_s: float
    reference: str | None


def _load_samples(wav_dir: Path) -> list[Sample]:
    samples: list[Sample] = []
    for wav in sorted(wav_dir.glob("*.wav")):
        try:
            audio, dur = load_wav_pcm16(wav)
        except WavFormatError as exc:
            log.warning("Skipping %s: %s", wav.name, exc)
            continue
        ref_path = wav.with_suffix(".txt")
        ref = ref_path.read_text(encoding="utf-8").strip() if ref_path.is_file() else None
        samples.append(Sample(path=wav, audio_pcm16=audio, duration_s=dur, reference=ref))
    return samples


def _load_parakeet(model_path: Path, quantization: str, providers: list[str]) -> Any:
    """Load a Parakeet ONNX model directly via :mod:`onnx_asr`.

    ``ParakeetAsr`` hard-codes ``quantization="int8"``; for the FP32 column we
    need a second load, so we talk to ``onnx_asr`` directly here.
    """
    import onnx_asr  # type: ignore[import-not-found]

    providers = list(dict.fromkeys(providers))
    log.info("Loading Parakeet (%s) from %s providers=%s", quantization, model_path, providers)
    return onnx_asr.load_model(
        "nemo-parakeet-tdt-0.6b-v3",
        path=str(model_path),
        quantization=quantization,
        providers=providers,
    )


def _parakeet_transcribe(model: Any, audio_pcm16: bytes, language: str) -> str:
    samples = np.frombuffer(audio_pcm16, dtype=np.int16).astype(np.float32) / 32768.0
    kwargs: dict[str, Any] = {}
    if language and language != "auto":
        kwargs["language"] = language
    result = model.recognize(samples, **kwargs)
    if isinstance(result, list) and result:
        return str(result[0]).strip()
    return str(result).strip()


def _whisper_transcribe(model: Any, audio_pcm16: bytes) -> str:
    audio_f32 = np.frombuffer(audio_pcm16, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _info = model.transcribe(
        audio_f32,
        initial_prompt=_WHISPER_INITIAL_PROMPT,
        beam_size=5,
    )
    return " ".join(seg.text.strip() for seg in segments).strip()


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _render_markdown(
    samples: list[Sample],
    rows: list[dict[str, str]],
    columns: list[str],
) -> str:
    lines: list[str] = []
    lines.append("# Parakeet accuracy comparison")
    lines.append("")
    lines.append(
        "Run this harness with ``scripts/compare_accuracy.py``; then manually "
        "tag errors (substitution / deletion / insertion) per cell."
    )
    lines.append("")
    header = ["file", "dur"] + columns
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for sample, row in zip(samples, rows):
        cells = [sample.path.name, f"{sample.duration_s:.1f}s"]
        for col in columns:
            cells.append(_md_escape(row.get(col, "")))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="compare_accuracy",
        description="Accuracy comparison harness (Parakeet INT8 / FP32 / Whisper).",
    )
    parser.add_argument("--wav-dir", type=Path, required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("accuracy_comparison.md"),
        help="Markdown table output path (default: ./accuracy_comparison.md).",
    )
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--fixups", type=Path, default=Path("vocab_fixups.json"))
    parser.add_argument(
        "--fp32-path",
        type=Path,
        default=None,
        help="Directory with FP32 Parakeet ONNX files. Omit to skip the FP32 column.",
    )
    parser.add_argument(
        "--whisper",
        action="store_true",
        help="Include Whisper large-v3 via faster-whisper (must be pip-installed separately).",
    )
    parser.add_argument(
        "--whisper-model",
        default="large-v3",
        help="faster-whisper model name (default: large-v3).",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

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

    config = load_config(args.config)
    fixups = FixupEngine(args.fixups)

    samples = _load_samples(args.wav_dir)
    if not samples:
        print(f"No benchmarkable WAV files in {args.wav_dir}", file=sys.stderr)
        return 2
    log.info("Loaded %d sample(s)", len(samples))

    columns: list[str] = []
    if any(s.reference for s in samples):
        columns.append("reference")
    columns.append("parakeet_int8")

    providers = [config.asr.encoder_provider, "CPUExecutionProvider"]

    int8 = _load_parakeet(Path(config.asr.model_path), "int8", providers)

    fp32 = None
    if args.fp32_path is not None:
        if not args.fp32_path.is_dir():
            print(f"--fp32-path not found: {args.fp32_path}", file=sys.stderr)
            return 2
        fp32 = _load_parakeet(args.fp32_path, "fp32", providers)
        columns.append("parakeet_fp32")

    whisper = None
    if args.whisper:
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        except ImportError:
            print(
                "faster-whisper is not installed. Install it separately "
                "(`pip install faster-whisper`) or drop the --whisper flag.",
                file=sys.stderr,
            )
            return 2
        log.info("Loading Whisper %s (CPU int8)…", args.whisper_model)
        whisper = WhisperModel(args.whisper_model, device="cpu", compute_type="int8")
        columns.append("whisper_large_v3")

    rows: list[dict[str, str]] = []
    for sample in samples:
        row: dict[str, str] = {}
        if sample.reference is not None:
            row["reference"] = sample.reference

        t0 = time.perf_counter()
        int8_text = _parakeet_transcribe(int8, sample.audio_pcm16, config.asr.language)
        row["parakeet_int8"] = fixups.apply(int8_text)
        log.info("%s int8 %.0fms: %s", sample.path.name, (time.perf_counter() - t0) * 1000, row["parakeet_int8"][:80])

        if fp32 is not None:
            t0 = time.perf_counter()
            fp32_text = _parakeet_transcribe(fp32, sample.audio_pcm16, config.asr.language)
            row["parakeet_fp32"] = fixups.apply(fp32_text)
            log.info("%s fp32 %.0fms: %s", sample.path.name, (time.perf_counter() - t0) * 1000, row["parakeet_fp32"][:80])

        if whisper is not None:
            t0 = time.perf_counter()
            row["whisper_large_v3"] = _whisper_transcribe(whisper, sample.audio_pcm16)
            log.info("%s whisper %.0fms: %s", sample.path.name, (time.perf_counter() - t0) * 1000, row["whisper_large_v3"][:80])

        rows.append(row)

    markdown = _render_markdown(samples, rows, columns)
    args.out.write_text(markdown, encoding="utf-8")
    log.info("Wrote %s (%d rows × %d columns)", args.out, len(rows), len(columns))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
