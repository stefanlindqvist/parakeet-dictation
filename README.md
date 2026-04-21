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

Default hotkey is **`Ctrl+Shift+Space`** (configurable in [config.toml](config.toml)). Hold to record, release to transcribe-and-paste. Startup logs `Ready. Hotkey=<ctrl>+<shift>+<space> …` once the ASR model has loaded and warmed up — only start dictating after that line.

Hotkeys to avoid on Windows 11 / Swedish layouts:
- **`Win+`` ` ``** — Windows Terminal's quake-mode shortcut grabs it at the OS level; pynput never sees the keystroke.
- **`Ctrl+Alt+X`** — on European (Swedish/German/…) layouts, `AltGr` sends `Ctrl+Alt` at the scan-code level, which would false-trigger on every AltGr shortcut.

## First-run smoke test

Open Notepad (or any text field), hold the hotkey, say:

> "Install the Dependabot workflow for the fitnesscoach repo, then configure pgvector with Qdrant as a secondary store."

Expected: every technical term lands correctly either from Parakeet directly or via `vocab_fixups.json`. If not, add a substitution entry and reload the daemon.

## Configuration

All runtime tuning lives in [config.toml](config.toml). Keys mirror [AppConfig](src/parakeet_dictation/config.py):

| Section    | Key                    | Meaning                                                                                     |
|------------|------------------------|---------------------------------------------------------------------------------------------|
| `hotkey`   | `mode`                 | `hold` (record while held) or `toggle` (tap to start, tap to stop).                         |
| `hotkey`   | `key`                  | pynput chord notation, e.g. `<ctrl>+<shift>+<space>`, `<cmd>+<f9>`. See warnings above.     |
| `audio`    | `sample_rate`          | Fixed at `16000` for Parakeet. Do not change.                                               |
| `audio`    | `device_index`         | `-1` = default input. Use `python -m sounddevice` to list device indices.                   |
| `audio`    | `silence_timeout_ms`   | Toggle mode only: auto-stop after this much silence. Ignored in hold mode.                  |
| `vad`      | `enabled`              | Silero VAD on/off. Off = send the whole buffer to ASR unchanged.                            |
| `vad`      | `threshold`            | Silero confidence cutoff, 0.0–1.0. Raise if background noise triggers false speech.         |
| `vad`      | `min_speech_ms`        | Drop speech bursts shorter than this (accidental key taps, throat clears).                  |
| `asr`      | `model_path`           | Directory with the four ONNX files. Default matches `download_models.ps1` output.           |
| `asr`      | `language`             | `auto` (Parakeet detects), or ISO code (`en`, `sv`, …) to pin.                              |
| `asr`      | `encoder_provider`     | `DmlExecutionProvider` (GPU) or `CPUExecutionProvider`.                                     |
| `asr`      | `decoder_provider`     | `CPUExecutionProvider` is intentional — see handover §3. Don't flip to GPU.                 |
| `paste`    | `restore_clipboard`    | Snapshot + restore existing clipboard contents around the paste.                            |
| `paste`    | `restore_delay_ms`     | Wait this long after `Ctrl+V` before restoring, so the target app consumes the paste first. |
| `logging`  | `level`                | `DEBUG` / `INFO` / `WARNING` / `ERROR`.                                                     |
| `logging`  | `file`                 | Rotating log file path; rolls at 2 MB, keeps 3 backups.                                     |

Override the config path with `python -m parakeet_dictation --config path/to/other.toml`.

Technical-vocabulary fixups — ordered regex substitutions applied post-transcription — live in [vocab_fixups.json](vocab_fixups.json) and are iterative: add an entry any time you spot a mis-transcription of a name you care about. Longer phrases before shorter ones; left side is Python `re` syntax with word boundaries.

## Architecture

```
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  Global hotkey   │ ───► │  Mic capture     │ ───► │  Silero VAD      │
│  (Ctrl+Shift+Spc)│      │  16 kHz mono     │      │  (trim silence)  │
└──────────────────┘      └──────────────────┘      └────────┬─────────┘
                                                             │
                                                             ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  Paste active    │ ◄─── │  Clipboard +     │ ◄─── │  Parakeet ONNX   │
│  window          │      │  vocab fixup     │      │  DirectML EP     │
└──────────────────┘      └──────────────────┘      └──────────────────┘
```

Parakeet encoder runs on the GPU (DirectML); decoder runs on the CPU (kernel-launch overhead dominates GPU on the TDT decoder's many small sequential calls). See handover Section 3 for why.

Each transcription emits a single log line with a latency breakdown (`rec / vad / asr / fixup / paste` in ms) — grep it to find slow stages.

## Troubleshooting

- **DirectML silently falls back to CPU.** At startup the daemon logs `ASR session <name> providers: […]`. If the encoder session shows only `CPUExecutionProvider`, update the NVIDIA GeForce driver and verify DirectX 12 support (`dxdiag`).
- **Hotkey conflicts with a Windows shortcut.** Change `hotkey.key` in [config.toml](config.toml). pynput notation: `<cmd>` = Win, `<ctrl>` / `<alt>` / `<shift>`, `<f1>`–`<f24>`, single characters (`` ` ``, `a`, etc.).
- **Paste arrives mangled in VS Code.** The Claude Code extension occasionally strips newlines from clipboard paste; raise `paste.restore_delay_ms` to ≥ 700 ms. A `SendInput` typing fallback is on the roadmap (handover §12).
- **First transcription is slow (2–3 s).** Expected — model warmup runs on startup. The `Ready.` log line appears only after warmup completes; start dictating then.
- **`onnxruntime` conflict.** If you ever see `CUDAExecutionProvider` offered but DirectML missing, you've got a second `onnxruntime-*` wheel installed. `pip uninstall onnxruntime onnxruntime-gpu` and reinstall `onnxruntime-directml`.
- **Model files missing.** The daemon fails loudly with `ASR model path does not exist …`. Run `pwsh scripts/download_models.ps1` once and retry.
- **Git Bash `ssh`/`scp` from PowerShell.** When pushing from Claude Code, the Git-bundled `ssh.exe` can't talk to the Windows ssh-agent named pipe. Prepend `C:\Windows\System32\OpenSSH` to `PATH` in PowerShell, or invoke the native `ssh.exe` by full path. Global note in `~/.claude/CLAUDE.md`.

## Training data / correction mining

The daemon appends a JSONL record to `training_data/events.jsonl` after every successful paste, and a companion hook (`scripts/claude_hook.py`) appends a record for every prompt you submit to Claude Code. Later, a correlator script can pair the two by time + similarity and surface "dictation X became submission Y" — that's the raw signal for growing [vocab_fixups.json](vocab_fixups.json).

The `training_data/` folder is `.gitignore`d (transcripts are user-specific and potentially sensitive). Disable logging entirely by setting `corpus.enabled = false` in [config.toml](config.toml).

**Wire the Claude Code hook once**, in `%USERPROFILE%\.claude\settings.json` (global — fires across every project):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python D:\\ClaudeProjects\\Dictation\\scripts\\claude_hook.py D:\\ClaudeProjects\\Dictation\\training_data\\events.jsonl"
          }
        ]
      }
    ]
  }
}
```

The hook uses stdlib only, never blocks your prompt (any failure exits 0 + stderr log), and stays silent on stdout so Claude's prompt context isn't polluted. Record schema is documented in [src/parakeet_dictation/events.py](src/parakeet_dictation/events.py).

## Benchmarks

Two offline harnesses under [scripts/](scripts/). Both take a directory of 16 kHz mono 16-bit WAV files (`ffmpeg -ar 16000 -ac 1 -sample_fmt s16 in.wav out.wav` converts anything else).

**Latency — handover §9b** ([scripts/bench.py](scripts/bench.py)):

```powershell
python scripts/bench.py --wav-dir ./samples --runs 5
```

Runs VAD → ASR → fixups against each WAV, reports per-file p50/p95/p99 plus aggregate stats and a pass/fail verdict for the 500 ms / 15 s-prompt target. Mic capture and paste are intentionally excluded (not deterministic). `--no-vad` and `--no-fixups` toggle stages off for isolating them.

**Accuracy — handover §9c** ([scripts/compare_accuracy.py](scripts/compare_accuracy.py)):

```powershell
# Minimum: INT8 column only
python scripts/compare_accuracy.py --wav-dir ./samples --out accuracy.md

# Add FP32 and Whisper large-v3 columns
pip install faster-whisper
python scripts/compare_accuracy.py --wav-dir ./samples --out accuracy.md `
    --fp32-path ./models/parakeet-tdt-0.6b-v3-fp32 --whisper
```

Runs each WAV through Parakeet INT8 + fixups, optionally Parakeet FP32 + fixups, optionally Whisper large-v3 + technical-vocabulary `initial_prompt`. Writes a markdown table ready for manual error tagging. If a WAV has a sibling `<name>.txt` file, it's included as a `reference` column. `faster-whisper` is *not* a project dependency — install it separately when you want that column.

## Project layout

See handover Section 5 for the canonical tree. All core modules under [src/parakeet_dictation/](src/parakeet_dictation/) are implemented:

- [config.py](src/parakeet_dictation/config.py) — pydantic-settings loader for `config.toml`.
- [asr.py](src/parakeet_dictation/asr.py) — `onnx-asr` Parakeet wrapper, hybrid GPU/CPU provider split.
- [fixups.py](src/parakeet_dictation/fixups.py) — ordered regex substitutions from `vocab_fixups.json`.
- [paste.py](src/parakeet_dictation/paste.py) — Win32 clipboard snapshot/restore + `SendInput` `Ctrl+V`.
- [audio.py](src/parakeet_dictation/audio.py) — `sounddevice` 16 kHz mono PCM capture.
- [vad.py](src/parakeet_dictation/vad.py) — Silero VAD (ONNX, CPU) trim / drop.
- [daemon.py](src/parakeet_dictation/daemon.py) — asyncio main loop, hotkey wiring, latency logging.
- [__main__.py](src/parakeet_dictation/__main__.py) — CLI entry, logging setup.

## Status

MVP pipeline complete: record → VAD → Parakeet (DirectML encoder + CPU decoder) → fixups → paste. Benchmark and accuracy comparison harnesses (handover §9b, §9c) in place. Next up: run both against a real sample corpus to validate the <500 ms SLO and decide INT8-vs-FP32, then the Rust port (handover §10a).
