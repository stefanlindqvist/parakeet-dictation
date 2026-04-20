# parakeet-dictation

Local, push-to-talk speech-to-text dictation daemon for Windows 11. Hold a hotkey, speak, release — the transcript is pasted into the active window. Runs **fully offline** using Parakeet-TDT 0.6B v3 via ONNX Runtime DirectML on the system GPU; no CUDA Toolkit, no cloud APIs, no subscriptions.

Canonical design and rationale: [parakeet-dictation-handover.md](parakeet-dictation-handover.md). This README is the operator's quickstart; the handover is the engineering spec.

## Hard constraints

- Windows 11 (24H2+). Linux/macOS not supported.
- Python 3.11 or 3.12 (not 3.13 — ONNX Runtime DirectML wheels lag).
- **No CUDA Toolkit install** (past BSOD from NVIDIA Nsight kernel components). DirectML uses only the existing GeForce display driver.
- No `onnxruntime` or `onnxruntime-gpu` in the venv — only `onnxruntime-directml`. They conflict.
- Offline after first-run: no telemetry, no cloud ASR.

## Quick start

```powershell
# 1. Create venv + install (from the repo root)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]

# 2. Download Parakeet ONNX models (~670 MB int8)
pwsh scripts/download_models.ps1

# 3. Review / edit config.toml (hotkey, audio device, language)

# 4. Run the daemon
python -m parakeet_dictation
```

Default hotkey is `Win+`` ` `` (configurable in `config.toml`). Hold to record, release to transcribe-and-paste.

## Configuration

All runtime tuning lives in [config.toml](config.toml) (hotkey mode, audio device, VAD threshold, ASR providers, paste behaviour, log level). Technical-vocabulary fixups — regex substitutions applied post-transcription — live in [vocab_fixups.json](vocab_fixups.json) and are iterative: add entries as you spot mis-transcriptions.

## Architecture

```
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  Global hotkey   │ ───► │  Mic capture     │ ───► │  Silero VAD      │
│  (Win+`)         │      │  16 kHz mono     │      │  (trim silence)  │
└──────────────────┘      └──────────────────┘      └────────┬─────────┘
                                                             │
                                                             ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  Paste active    │ ◄─── │  Clipboard +     │ ◄─── │  Parakeet ONNX   │
│  window          │      │  vocab fixup     │      │  DirectML EP     │
└──────────────────┘      └──────────────────┘      └──────────────────┘
```

Parakeet encoder runs on the GPU (DirectML); decoder runs on the CPU (kernel-launch overhead dominates GPU on the TDT decoder's many small sequential calls). See handover Section 3 for why.

## Troubleshooting

- **DirectML silently falls back to CPU.** `daemon.py` logs the actual execution provider in use at startup. If you see `CPUExecutionProvider` for the encoder, update the NVIDIA GeForce driver and re-check DirectX 12 support.
- **Hotkey conflicts with a Windows shortcut.** Change `hotkey.key` in `config.toml` (pynput notation, e.g. `"<cmd>+<f12>"`).
- **Paste arrives mangled in VS Code.** The Claude Code extension sometimes strips newlines from clipboard paste; consider `paste.restore_delay_ms` ≥ 700 ms or fall back to character-by-character `SendInput` (planned — see handover Section 12).
- **First transcription is slow (2–3 s).** Expected — model warmup runs on startup. The log line `Ready` appears only after warmup completes; start dictating then.
- **Git Bash `ssh`/`scp` from PowerShell.** When pushing from Claude Code, the Git-bundled `ssh.exe` can't talk to the Windows ssh-agent named pipe. Prepend `C:\Windows\System32\OpenSSH` to `PATH` in PowerShell, or invoke the native `ssh.exe` by full path. Global note in `~/.claude/CLAUDE.md`.

## Project layout

See handover Section 5 for the canonical tree. Skeleton modules under [src/parakeet_dictation/](src/parakeet_dictation/) raise `NotImplementedError` today; implement in the order of handover Section 11.

## Status

Scaffold only. No module is implemented yet. Implementation tracked against handover Section 11.
