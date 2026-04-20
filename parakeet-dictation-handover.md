# Local Speech-to-Text Dictation Daemon — Handover Document

**Target platform:** Windows 11, Python-first (Rust port path preserved)
**Hardware:** AMD 9800X3D, 32 GB RAM, NVIDIA RTX 5080 (Blackwell, 16 GB VRAM)
**Use case:** Push-to-talk dictation into the active Windows application, primarily VS Code running the Claude Code extension
**Author context:** Solution Architect in Gothenburg, Sweden. Developer with Rust + C# focus. Values details, avoids shortcuts, prefers local self-hosted over paid SaaS.

---

## 1. Problem Statement

The user wants a fast, accurate, **fully local** speech-to-text dictation tool that:

- Works reliably with developer/technical vocabulary (e.g. `Dependabot`, `pgvector`, `Qdrant`, `Gluetun`, `qBittorrent`, `CIDR`, Rust crate names, Microsoft Graph API endpoints, Synology services).
- Pastes transcription into any active Windows application — especially VS Code with the Claude Code extension.
- Supports at minimum English, with occasional Swedish.
- Does **not** require installing the NVIDIA CUDA Toolkit on the host system. A previous attempt resulted in a Windows BSOD (`UNEXPECTED_KERNEL_MODE_TRAP`) caused by NVIDIA Nsight kernel components bundled with the CUDA SDK. Avoiding a CUDA toolkit install is a hard constraint.
- Costs nothing (local compute only, no SaaS subscriptions).

## 2. Options Evaluated

Three local approaches were considered:

### 2a. Parakeet-TDT 0.6B v3 via NeMo toolkit (rejected)

Highest-accuracy reference implementation, but NeMo pulls in PyTorch, PyTorch Lightning, Hydra, sentencepiece, and requires PyTorch compiled for `sm_120` (Blackwell). On Windows with an RTX 5080, this currently requires PyTorch Nightly with cu128 or cu129 — not yet fully stable. Also requires either the CUDA Toolkit or a PyTorch build bundling its own CUDA runtime. Too fragile for the hard "no CUDA toolkit" constraint.

### 2b. Whisper large-v3 via faster-whisper (viable fallback)

Mature ecosystem, broad Windows support, supports initial-prompt conditioning for custom vocabulary. Runs via CTranslate2 with its own bundled CUDA libs. Real-world accuracy on technical terms is acceptable but **measurably worse** than Parakeet-TDT on numbers and technical terminology. Kept as a fallback if Parakeet setup becomes problematic.

### 2c. Parakeet-TDT 0.6B v3 via ONNX Runtime + DirectML (CHOSEN)

**This is the target architecture.** Key properties:

- Uses **ONNX Runtime DirectML execution provider** — Windows' native GPU API. Works on any DirectX 12 GPU without the CUDA Toolkit. Uses only the existing NVIDIA GeForce display driver.
- Parakeet-TDT 0.6B v3 is #1 on the Hugging Face Open ASR Leaderboard (6.05% average WER) and outperforms Whisper on technical terms, numbers, and punctuation handling.
- Multilingual: 25 European languages including English and Swedish, with automatic language detection.
- Fast: on a 5080 with DirectML, end-to-end latency for a 15-second prompt is expected to be sub-500ms.
- Pre-exported ONNX models exist on Hugging Face (`onnx-community/parakeet-tdt-0.6b-v3-ONNX`). No model conversion step needed.
- Inference library `onnx-asr` handles preprocessing (mel-filterbank), TDT decoding, and tokenizer without requiring PyTorch, NeMo, or Transformers.
- Rust port path is preserved: the `parakeet-rs` crate (https://github.com/altunenes/parakeet-rs) implements the same ONNX inference pipeline in pure Rust. Port the daemon to Rust later once Python ergonomics are validated.

## 3. Architecture

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

**Flow:**

1. User holds (or taps) a global hotkey (default `Win+`` `` ` ``, configurable).
2. Microphone captures 16 kHz mono PCM audio via `sounddevice`.
3. On release (or VAD silence detection), audio buffer is passed to Silero VAD (ONNX) to trim leading/trailing silence and reject false triggers.
4. Trimmed audio is fed to Parakeet-TDT 0.6B v3 encoder (GPU via DirectML) and decoder (CPU — see note below).
5. Transcript goes through a `vocab_fixups.json` post-processing pass that normalises known substitution patterns (e.g. `"gleeton" → "Gluetun"`).
6. Final text is placed on the Windows clipboard and a `Ctrl+V` is simulated into the active window.

**Hybrid GPU/CPU decoding note:** The Parakeet encoder benefits from GPU parallelism (single-pass over entire audio). The TDT decoder runs hundreds of small sequential inference calls per transcription — GPU kernel launch overhead dominates for these tiny operations, making CPU 3–6× faster for the decoder stage. The `clarity-scribe` project documents this trade-off empirically on Windows. The daemon should reflect this: `encoder` on `DmlExecutionProvider`, `decoder_joint` on `CPUExecutionProvider`.

## 4. Dependencies

### Python runtime
- **Python 3.11 or 3.12** (3.13 not yet mature for all ONNX Runtime wheels on Windows as of 2026-04).
- Create a venv: `python -m venv .venv` then `.\.venv\Scripts\Activate.ps1`.

### Python packages (all pip, no system CUDA)
- `onnx-asr` — Parakeet TDT inference (mel preprocessing, TDT greedy decoding, tokenizer).
- `onnxruntime-directml` — GPU acceleration on Windows via DirectX 12. **Do not** also install `onnxruntime` or `onnxruntime-gpu`; they conflict.
- `sounddevice` + `numpy` — microphone capture.
- `silero-vad` — voice activity detection (ships with bundled ONNX model).
- `pynput` — global hotkey listener (cross-platform; reliable on Windows).
- `pywin32` — native Windows clipboard + keystroke simulation (lower latency and more reliable than `pyautogui` in VS Code).
- `pydantic` + `pydantic-settings` — typed config from `config.toml`.
- `rich` — pleasant console logging during development.

### Model files (download once, ~900 MB int8 quantized)

From `https://huggingface.co/onnx-community/parakeet-tdt-0.6b-v3-ONNX`:
- `encoder-model.int8.onnx`
- `encoder-model.int8.onnx.data`
- `decoder_joint-model.int8.onnx`
- `vocab.txt` (or `tokenizer.json` depending on onnx-asr version)

Store in `./models/parakeet-tdt-0.6b-v3/`.

For reference: full precision (fp32) models are ~2.5 GB. INT8 is the right default — accuracy loss is negligible and speed improves significantly. A small validation script should compare both variants against a sample of the user's real prompts before committing to INT8 permanently.

## 5. Project Structure

```
parakeet-dictation/
├── pyproject.toml
├── README.md
├── config.toml                    # User-editable runtime config
├── vocab_fixups.json              # Term substitutions (iterative)
├── models/
│   └── parakeet-tdt-0.6b-v3/      # Downloaded ONNX files
├── src/
│   └── parakeet_dictation/
│       ├── __init__.py
│       ├── __main__.py            # Entry point: `python -m parakeet_dictation`
│       ├── config.py              # Pydantic config loader
│       ├── daemon.py              # Main daemon loop + hotkey wiring
│       ├── audio.py               # Mic capture via sounddevice
│       ├── vad.py                 # Silero VAD wrapper
│       ├── asr.py                 # onnx-asr wrapper, model loading
│       ├── fixups.py              # Post-processing vocab substitutions
│       └── paste.py               # Win32 clipboard + Ctrl+V simulation
├── scripts/
│   ├── download_models.ps1        # PowerShell model downloader
│   └── bench.py                   # Latency benchmark on sample audio
└── tests/
    ├── test_fixups.py
    └── test_config.py
```

## 6. Configuration Schema (`config.toml`)

```toml
[hotkey]
# Toggle mode: tap to start, tap to stop
# Hold mode: hold to record, release to transcribe
mode = "hold"                      # "hold" | "toggle"
key = "<cmd>+`"                    # pynput notation

[audio]
sample_rate = 16000
device_index = -1                  # -1 = default input device
# Silence detection — VAD terminates recording after this many ms of silence
# in toggle mode. Ignored in hold mode.
silence_timeout_ms = 1200

[vad]
enabled = true
threshold = 0.5                    # Silero confidence threshold
min_speech_ms = 200                # Ignore bursts shorter than this

[asr]
model_path = "./models/parakeet-tdt-0.6b-v3"
language = "auto"                  # "auto" | "en" | "sv" | ...
encoder_provider = "DmlExecutionProvider"
decoder_provider = "CPUExecutionProvider"

[paste]
# Restore clipboard after paste so we don't clobber what the user had
restore_clipboard = true
restore_delay_ms = 500

[logging]
level = "INFO"
file = "./parakeet-dictation.log"
```

## 7. Initial `vocab_fixups.json`

Seed with the user's known technical vocabulary. The structure is ordered (longer phrases before single words) and case-preserving for the replacement. Patterns use simple word-boundary regex on the left side.

```json
{
  "substitutions": [
    { "pattern": "\\bdependa ?bot\\b",          "replacement": "Dependabot" },
    { "pattern": "\\bgleeton\\b",               "replacement": "Gluetun" },
    { "pattern": "\\bgloo ?ten\\b",             "replacement": "Gluetun" },
    { "pattern": "\\bcue ?bit ?torrent\\b",     "replacement": "qBittorrent" },
    { "pattern": "\\bq bit torrent\\b",         "replacement": "qBittorrent" },
    { "pattern": "\\bpeak ?vector\\b",          "replacement": "pgvector" },
    { "pattern": "\\bpg ?vector\\b",            "replacement": "pgvector" },
    { "pattern": "\\bq ?drant\\b",              "replacement": "Qdrant" },
    { "pattern": "\\bcue ?drant\\b",            "replacement": "Qdrant" },
    { "pattern": "\\bsin ?ology\\b",            "replacement": "Synology" },
    { "pattern": "\\bhes ?tra\\b",              "replacement": "Hestra" },
    { "pattern": "\\banon ?in(?:e|a)\\b",       "replacement": "Anonine" },
    { "pattern": "\\bpro ?ton\\b(?= ?vpn)",     "replacement": "Proton" },
    { "pattern": "\\bgore ?tex\\b",             "replacement": "Gore-Tex" },
    { "pattern": "\\bss[dh] ?notif",            "replacement": "DSM notif" },
    { "pattern": "\\bclaude ?code\\b",          "replacement": "Claude Code" },
    { "pattern": "\\banthropic\\b",             "replacement": "Anthropic" },
    { "pattern": "\\bgar ?min\\b",              "replacement": "Garmin" },
    { "pattern": "\\bolama\\b",                 "replacement": "Ollama" },
    { "pattern": "\\bcrates ?i ?o\\b",          "replacement": "crates.io" },
    { "pattern": "\\btom ?l\\b",                "replacement": "TOML" },
    { "pattern": "\\bsider\\b(?= |$)",          "replacement": "CIDR" },
    { "pattern": "\\bsee i d r\\b",             "replacement": "CIDR" },
    { "pattern": "\\bjson\\b",                  "replacement": "JSON" },
    { "pattern": "\\byaml\\b",                  "replacement": "YAML" },
    { "pattern": "\\bdsm\\b",                   "replacement": "DSM" },
    { "pattern": "\\bn a s\\b",                 "replacement": "NAS" },
    { "pattern": "\\bm c p\\b",                 "replacement": "MCP" },
    { "pattern": "\\br a g\\b",                 "replacement": "RAG" },
    { "pattern": "\\bl l m\\b",                 "replacement": "LLM" },
    { "pattern": "\\bvs ?code\\b",              "replacement": "VS Code" },
    { "pattern": "\\brust(?:_|-)?lang\\b",      "replacement": "Rust" },
    { "pattern": "\\bpow ?er ?shell\\b",        "replacement": "PowerShell" }
  ]
}
```

The fixups module should load this once at startup, compile all patterns, and apply them in order on every transcript.

## 8. Key Implementation Notes

### 8a. `asr.py` — onnx-asr wrapper

- Load model once at startup; reuse the session for every transcription.
- Use `onnx-asr`'s Parakeet loader. Set `providers=["DmlExecutionProvider", "CPUExecutionProvider"]` for the encoder session.
- Note: the decoder_joint is loaded separately and should be constrained to CPU.
- Warm up the model at startup with ~1 second of silence to avoid first-call latency spikes.

### 8b. `paste.py` — Windows paste

Use `pywin32` directly rather than `pyautogui` / `keyboard`. Reasons:

- `OpenClipboard` / `SetClipboardData` / `CloseClipboard` is atomic and race-free.
- `SendInput` (via `win32api.keybd_event` or better `ctypes` with `SendInput`) reliably delivers `Ctrl+V` in all Windows apps including Electron (VS Code) and UWP apps, where `pyautogui` sometimes fails.
- Clipboard restore: snapshot current clipboard contents, set new text, send `Ctrl+V`, sleep `restore_delay_ms`, restore original clipboard.

### 8c. `vad.py` — Silero VAD

Use the ONNX build of Silero VAD (bundled with the `silero-vad` pip package as of v5.x). Run on CPU — it's a tiny model and GPU overhead isn't worth it. Feed it 30 ms windows of PCM-16 audio.

In **hold mode**, VAD is used only to trim leading/trailing silence from the recording.
In **toggle mode**, VAD additionally terminates recording after `silence_timeout_ms` of silence.

### 8d. `daemon.py` — lifecycle

- Use `asyncio` for the main loop.
- `pynput` runs its own thread — bridge to asyncio via `loop.call_soon_threadsafe`.
- Log every transcription event (timestamp, duration, latency breakdown: record / VAD / encode / decode / paste) to the log file for later tuning.
- Graceful shutdown on `Ctrl+C`: stop the hotkey listener, close ONNX sessions, flush log.

### 8e. First-run experience

Ship a `scripts/download_models.ps1` that:
1. Creates `./models/parakeet-tdt-0.6b-v3/`.
2. Downloads the four ONNX files from Hugging Face using `Invoke-WebRequest` (no external deps).
3. Verifies SHA-256 checksums.
4. Reports total size on completion.

## 9. Validation Plan

### 9a. Smoke test

After build, run `python -m parakeet_dictation` and dictate:

> "Install the Dependabot workflow for the fitnesscoach repo, then configure pgvector with Qdrant as a secondary store."

Expected: every technical term is correctly transcribed either directly by Parakeet or via the fixups layer.

### 9b. Latency benchmark (`scripts/bench.py`)

Run the daemon's full pipeline against a folder of recorded WAV files. Report:
- p50 / p95 / p99 end-to-end latency (audio end → clipboard write)
- Breakdown per stage (VAD / encode / decode / paste)

Target on RTX 5080 for a 15-second prompt: **< 500 ms end-to-end**.

### 9c. Accuracy comparison

Record 20 real prompts (mix of Claude Code prompts, shell commands, prose emails). Transcribe with:
1. Parakeet INT8 + fixups (the target)
2. Parakeet FP32 + fixups (to confirm INT8 is acceptable)
3. Whisper large-v3 via faster-whisper + initial prompt (as a sanity comparison)

Manually tag errors. Decide whether INT8 is good enough or FP32 is worth the extra VRAM and ~20% latency.

## 10. Future Enhancements (post-MVP)

### 10a. Rust port
Once Python ergonomics are validated and vocab fixups stabilise, port the daemon to Rust using:
- `parakeet-rs` crate for inference (same ONNX models, no re-export needed)
- `cpal` for audio capture
- `global-hotkey` crate for hotkeys
- `arboard` for clipboard
- `windows` crate for `SendInput`

Single-binary distribution, no Python runtime, matches the user's "high security credence" preference for steady services.

### 10b. Mode-specific prompts
Add support for multiple modes (Claude Code prompt mode, email mode, shell command mode) each with their own fixup dictionary. Switch via hotkey modifier.

### 10c. Integration with existing Ollama setup
Optional post-processing stage: after transcription + fixups, pipe through a local LLM (Qwen3 4B on the secondary machine) with a "clean up grammar, preserve technical terms exactly" prompt. Only for longer-form dictation (emails, docs), not for Claude Code prompts where raw speed matters.

### 10d. Telemetry dashboard
Local SQLite log of every transcription (audio duration, word count, latency stages, fixup hits). Build a small Grafana or Streamlit dashboard to spot accuracy regressions and identify new terms to add to fixups.

## 11. What Claude Code Should Build First

Recommended order of work (single session target: a runnable MVP):

1. **`pyproject.toml`** with all dependencies pinned.
2. **`scripts/download_models.ps1`** — user runs this first to pull models.
3. **`src/parakeet_dictation/config.py`** — Pydantic config loader.
4. **`src/parakeet_dictation/asr.py`** — load model, warm up, transcribe WAV bytes to text. Unit-test with a sample WAV.
5. **`src/parakeet_dictation/fixups.py`** — load JSON, apply regex substitutions. Unit-test thoroughly.
6. **`src/parakeet_dictation/paste.py`** — Win32 clipboard + Ctrl+V. Test in Notepad first.
7. **`src/parakeet_dictation/audio.py`** — mic capture with start/stop methods.
8. **`src/parakeet_dictation/vad.py`** — Silero wrapper.
9. **`src/parakeet_dictation/daemon.py`** — wire it all together with hotkey.
10. **`src/parakeet_dictation/__main__.py`** — CLI entry point.
11. **`README.md`** — install, first-run, config reference, troubleshooting.

Leave `scripts/bench.py` and the accuracy comparison harness for a second session.

## 12. Known Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `onnxruntime-directml` conflicts with another `onnxruntime-*` package in the venv | Medium | Pin exactly one in `pyproject.toml`; document clearly in README |
| DirectML provider falls back to CPU silently on some driver versions | Low | Log the actual provider in use at startup; error loudly if fallback occurs |
| `pynput` global hotkey conflicts with a Windows system shortcut | Medium | Default to `Win+`` `` ` ``; document how to change it |
| Parakeet mis-detects language on short English clips and outputs Swedish | Low | Allow pinning language in config; default to `"auto"` but provide `"en"` override |
| VS Code's Claude Code extension captures the paste in a way that strips newlines | Low | Test in actual VS Code extension early; fall back to typing characters via `SendInput` if clipboard paste misbehaves |
| Model download from Hugging Face hits rate limits | Low | Use `huggingface_hub` library with retry in the download script as a fallback to `Invoke-WebRequest` |
| First-call inference is slow (2-3s) making the first prompt feel broken | High | Warm up with silent audio at daemon startup; log "Ready" only after warm-up completes |

## 13. Hard Constraints Summary

- **No CUDA Toolkit install.** Only DirectML or CPU. Any library requiring `nvcc` or `cuda_runtime.dll` from the system is disqualified.
- **No NVIDIA Nsight components.** The original BSOD cause.
- **Windows-first.** Linux support can come later; target Windows 11 24H2+.
- **Python 3.11 or 3.12.** Not 3.13 (ONNX Runtime DirectML wheel availability).
- **Offline after first-run.** No cloud APIs, no telemetry phoning home.

## 14. References

- Parakeet-TDT 0.6B v3 model card: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3
- ONNX export of Parakeet: https://huggingface.co/onnx-community/parakeet-tdt-0.6b-v3-ONNX
- `onnx-asr` library: https://github.com/istupakov/onnx-asr
- `parakeet-rs` (Rust port reference): https://github.com/altunenes/parakeet-rs
- `clarity-scribe` (Electron reference implementation, documents the hybrid GPU/CPU decoding trade-off): https://github.com/laloquidity/clarity-scribe
- Silero VAD: https://github.com/snakers4/silero-vad
- ONNX Runtime DirectML EP: https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html

---

**End of handover. Open this in VS Code, start a Claude Code session, and work through Section 11 in order.**
