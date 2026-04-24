# Rust Port Scoping

Companion to [parakeet-dictation-handover.md](parakeet-dictation-handover.md) §10a. This document is the source of truth for *when* and *how* the Rust port happens. The handover's §10a is intentionally brief; this expands it into a concrete plan.

## Preconditions (do not start until all true)

1. Python MVP is in daily use and has survived at least two weeks of real dictation against VS Code + Claude Code — not just smoke tests.
2. `vocab_fixups.json` has stopped churning week-over-week. The fixup set is the main living artifact; churn in Rust is more expensive than in Python.
3. A latency + accuracy baseline is captured via `scripts/bench.py` and `scripts/accuracy.py` so the Rust port has a concrete target to match, not a subjective "feels right."

As of this writing the Python daemon has not yet been used in anger, so these preconditions are not met. Revisit this doc after the Python setup has been lived with.

## Phasing

### Phase 0 — spike (1–2 days, throwaway)

Goal: de-risk the two things most likely to kill the port before committing to a full rewrite.

- Load `encoder-model.int8.onnx` via the `ort` crate with the DirectML execution provider on the 5080. Encode ~10 s of audio. Compare encoder output tensors to the Python pipeline within floating-point tolerance.
- Run a hand-rolled TDT decode loop (via `ort` on CPU EP) against the decoder/joint model. Compare the transcript to Python on the same WAV.

If either fails, stop and re-scope. Don't start Phase 1 on a broken foundation.

### Phase 1 — headless parity CLI

`cargo run -- transcribe file.wav` prints the transcript to stdout. No hotkey, no paste, no VAD. Reuses the same `models/` directory and the same `vocab_fixups.json` as the Python daemon.

Ship criterion: WER on the 20-prompt accuracy set matches Python within noise (±0.5% absolute) and end-to-end latency is within 20% of Python.

### Phase 2 — daemon

Add hotkey, audio capture, VAD, and paste. Single-binary distribution. Behavior-compatible with the Python `config.toml` so users don't relearn configuration — see "Shared configuration schema" below.

### Phase 3 — cutover

Python stays in the repo as the fallback and reference implementation for at least one release cycle after the Rust daemon ships. `parakeet-dictation.exe` becomes the recommended entry point. Remove the Python daemon only after the Rust binary has run the user's daily workflow for two-plus weeks without a fallback event.

## Decisions

### Own the TDT decode — do not depend on `parakeet-rs`

The `parakeet-rs` crate is a thin single-maintainer project. The TDT greedy decode loop is on the order of 100 lines of code against `ort` directly. Rewriting it in-tree:

- Removes a sole-maintainer dependency risk on a piece of code that is central to the product.
- Makes the hybrid encoder-on-DML / decoder-on-CPU split (handover §3) a first-class in-repo design decision rather than something we inherit and hope stays true upstream.
- Avoids version-skew pain if `ort` ships a breaking change and `parakeet-rs` lags.

The `ort` crate is the only external ONNX Runtime dependency.

### Shared configuration schema

Python and Rust read the same `config.toml` during the transition. A divergence between the two schemas would force users to maintain two configs and would make the Phase 3 cutover a breaking change. Keep one schema, one file, one source of truth.

Implementation notes:

- `serde` structs on the Rust side mirror the `pydantic` models in [config.py](src/parakeet_dictation/config.py).
- New config fields are added in Python first, then mirrored in Rust — Python is still the reference during the transition.
- A parity test reads `config.toml` through both loaders and asserts the resulting structures are equivalent.

### Sibling crate in this repo

The Rust code lives at `rust/` (or similar) inside this repo until cutover, not in a separate `parakeet-dictation-rs` repository. Rationale:

- Single place to review cross-language parity changes (fixups, config schema, model versions).
- One issue tracker, one PR history.
- Split into a separate repo only if/when the Python daemon is deleted in Phase 3 and a clean Rust-only history is worth the break.

## Crate mapping

| Layer              | Crate                              | Notes                                                                                                                   |
| ------------------ | ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| ONNX inference     | `ort` 2.x                          | Direct dependency. DirectML EP for encoder, CPU EP for decoder/joint — same split as Python.                            |
| Parakeet decoder   | hand-rolled over `ort`             | ~100 LOC of TDT greedy decode. See decision above.                                                                      |
| Audio capture      | `cpal`                             | Mature, cross-platform. Mirrors `sounddevice`.                                                                          |
| VAD                | `ort` + bundled Silero ONNX        | Not named in §10a. No first-class Rust Silero crate — run the same ONNX model through `ort` on CPU, as Python does.     |
| Hotkey             | `global-hotkey` (tauri)            | Verify it can bind `Win+\`` specifically; `pynput` handles it today.                                                    |
| Clipboard          | `arboard`                          | Read/write only — it does not simulate keystrokes.                                                                      |
| Paste keystroke    | `windows` crate `SendInput`        | Direct Win32 call; mirrors [paste.py](src/parakeet_dictation/paste.py).                                                 |
| Regex fixups       | `fancy-regex`, **not `regex`**     | [vocab_fixups.json](vocab_fixups.json) uses lookaheads (`(?=...)`) in ~9 patterns. The default `regex` crate rejects these. |
| Config             | `serde` + `toml`                   | Straight port of [config.py](src/parakeet_dictation/config.py). Shared schema — see decision above.                     |
| Async runtime      | `tokio`                            | Matches the asyncio structure in [daemon.py](src/parakeet_dictation/daemon.py).                                         |
| Logging            | `tracing` + `tracing-subscriber`   | Replaces `rich`.                                                                                                        |

## Out of scope for the first Rust release

- Handover §10b mode-specific prompts, §10c Ollama post-processing, §10d telemetry dashboard. Stabilize these in Python first, then port.
- Installer, code signing, auto-update. Defer until the binary has proven itself.
- Cross-platform (macOS, Linux). Still Windows-first per handover §13.

## Known risks

| Risk                                                                       | Mitigation                                                                                                          |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `ort` + DirectML on Blackwell (5080) silently falls back to CPU            | Log the active EP at startup; fail loudly on fallback, same as the Python daemon does today.                        |
| `fancy-regex` performance regression vs Python `re` on the fixup pass      | Benchmark the fixup pass against the Python baseline in Phase 1; the set is small enough that this is unlikely.     |
| `global-hotkey` can't bind the `Win+\`` combination                        | Catch in Phase 2 spike; fall back to a different default hotkey if needed, document in README.                      |
| TDT decode parity drift between the hand-rolled Rust decoder and Python    | Phase 1 ships with a per-file parity test on the 20-prompt set; any drift is a release blocker.                     |
| Clipboard restore timing differs between `arboard` + `SendInput` and pywin32 | Port the `restore_delay_ms` knob verbatim; manual-test in VS Code, Electron apps, and UWP apps before Phase 3.    |

## Open items (not decisions yet — revisit at Phase 0)

- Exact crate name for the sibling Rust project (`rust/`, `rust-daemon/`, `parakeet-dictation-rs/` as a workspace member). Decide when creating the Cargo workspace.
- Whether to vendor Silero's ONNX file in-repo or continue downloading it through the Python `silero-vad` package on first run. Leaning toward vendoring for the Rust build since there is no Rust `silero-vad` equivalent.
