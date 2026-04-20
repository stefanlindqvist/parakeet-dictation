# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

parakeet-dictation is a local, Windows-first push-to-talk speech-to-text dictation daemon. User holds a global hotkey, speaks, releases — the transcript is pasted into the active Windows application (primary target: VS Code with the Claude Code extension). Runs fully offline on Parakeet-TDT 0.6B v3 via ONNX Runtime DirectML (Windows-native GPU path via DirectX 12, no CUDA Toolkit). Supports English with occasional Swedish.

Canonical design: [parakeet-dictation-handover.md](parakeet-dictation-handover.md) is the source of truth for every design decision. When in doubt, read that doc.

## Tech Stack

- **Runtime**: Python 3.11 or 3.12 (not 3.13)
- **ASR model**: Parakeet-TDT 0.6B v3 (ONNX int8) from `istupakov/parakeet-tdt-0.6b-v3-onnx` (the `onnx-community/...` path cited in the handover does not exist; use this mirror, same author as `onnx-asr`)
- **Inference**: `onnx-asr` + `onnxruntime-directml` (encoder on `DmlExecutionProvider`, decoder on `CPUExecutionProvider`)
- **VAD**: `silero-vad` (ONNX, CPU)
- **Audio**: `sounddevice` (16 kHz mono PCM)
- **Hotkey + paste**: `pynput` (global hotkey), `pywin32` (Win32 clipboard + `SendInput` for `Ctrl+V`)
- **Config**: `pydantic` + `pydantic-settings` reading `config.toml`
- **Logging**: `rich`
- **Tests**: `pytest`

## Commands

```powershell
# Install (editable, with dev extras)
pip install -e .[dev]

# Run the daemon
python -m parakeet_dictation

# Run tests
pytest tests/ -v

# Download ONNX models (one-time, ~670 MB int8)
pwsh scripts/download_models.ps1
```

## Architecture

Pipeline (see [parakeet-dictation-handover.md](parakeet-dictation-handover.md) Section 3 for the ASCII diagram):

1. `pynput` global hotkey fires (`daemon.py`) → starts mic capture via `sounddevice` (`audio.py`).
2. On release (hold mode) or VAD silence (toggle mode), audio is trimmed by Silero VAD (`vad.py`).
3. Trimmed audio → `onnx-asr` Parakeet wrapper (`asr.py`): encoder on GPU (DirectML), decoder on CPU.
4. Raw transcript → `fixups.py` applies ordered regex substitutions from `vocab_fixups.json`.
5. Final text → `paste.py`: snapshot clipboard, `SetClipboardData`, simulate `Ctrl+V`, restore clipboard after `paste.restore_delay_ms`.

The **hybrid GPU/CPU split** for the encoder and decoder is intentional and load-bearing: the TDT decoder makes hundreds of small sequential inference calls; GPU kernel-launch overhead dominates and makes CPU 3–6× faster there. Don't "optimise" this by putting the decoder on the GPU — it's slower. See handover Section 3 for the empirical data.

### Project layout

```
src/parakeet_dictation/       # Skeleton today; implement per handover §11
├── __main__.py               # `python -m parakeet_dictation` entry
├── config.py                 # Pydantic loader for config.toml
├── daemon.py                 # asyncio main loop, hotkey wiring
├── audio.py                  # sounddevice mic capture
├── vad.py                    # Silero VAD wrapper
├── asr.py                    # onnx-asr Parakeet wrapper
├── fixups.py                 # vocab_fixups.json regex engine
└── paste.py                  # Win32 clipboard + SendInput Ctrl+V
scripts/download_models.ps1   # One-time model downloader (functional)
scripts/bench.py              # Latency benchmark (stub)
tests/test_config.py          # Config loader tests (skipped until §11 step 3)
tests/test_fixups.py          # Fixup engine tests (skipped until §11 step 5)
```

## Hard Constraints

From handover Section 13. **Do not violate these** — past incidents informed them.

- **No CUDA Toolkit install.** Only DirectML or CPU. Any library requiring `nvcc` or `cuda_runtime.dll` from the system is disqualified. Past BSOD (`UNEXPECTED_KERNEL_MODE_TRAP`) was caused by NVIDIA Nsight kernel components bundled with the CUDA SDK.
- **No NVIDIA Nsight components.** The original BSOD cause.
- **Windows 11 only** for now. Linux/macOS support can come later.
- **Python 3.11 or 3.12** (not 3.13 — ONNX Runtime DirectML wheel gap).
- **`onnxruntime-directml` is the only `onnxruntime-*` package in the venv.** Installing `onnxruntime` or `onnxruntime-gpu` alongside breaks DirectML silently.
- **Offline after first-run.** No cloud ASR, no telemetry.

## Conventions

- Config is read once at startup; modules accept a config object in `__init__`, not a path.
- The ASR session is loaded once and reused. Warm up with ~1 s of silent audio on startup; only then log `Ready`.
- Every transcription logs a latency breakdown (record / VAD / encode / decode / paste) for later tuning.
- PowerShell scripts use `pwsh` (PowerShell 7+), not `powershell.exe`, unless they must run on a default Windows 11 install with no pwsh — `scripts/download_models.ps1` is an exception (it runs before the user has done anything, so it sticks to built-in Windows PowerShell 5.1 syntax).

## Reference

- Canonical spec: [parakeet-dictation-handover.md](parakeet-dictation-handover.md)
- Implementation order: handover Section 11 (build `pyproject.toml` → `download_models.ps1` → `config.py` → `asr.py` → `fixups.py` → `paste.py` → `audio.py` → `vad.py` → `daemon.py` → `__main__.py` → `README.md` additions)
