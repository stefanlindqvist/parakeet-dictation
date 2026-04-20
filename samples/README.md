# Sample corpus for bench + accuracy harnesses

15 scripted prompts (this folder) + ~5 ad-lib prompts (you add) = 20-prompt corpus for [scripts/bench.py](../scripts/bench.py) and [scripts/compare_accuracy.py](../scripts/compare_accuracy.py), per handover §9c.

## Category mix

| # | File pattern | Category | Stresses |
|---|---|---|---|
| 01–05 | `promptNN_claudecode_*.txt` | Claude Code prompts | Dependabot, pgvector, Qdrant, MCP, SendInput, crates.io, Ollama, RAG, DSM, Synology, NAS |
| 06–09 | `promptNN_shell_*.txt` | Shell / PowerShell | port numbers, qBittorrent, Gluetun, CIDR, TOML, Rust, Blackwell |
| 10–12 | `promptNN_email_*.txt` | Prose emails | Anthropic, Claude Code, Proton VPN, Anonine, Hestra, Gore-Tex |
| 13–14 | `promptNN_swedish_*.txt` | Swedish | code-switching, umlauts, Garmin, Ollama, Qdrant mentioned in Swedish sentences |
| 15 | `prompt15_numbers_cidr.txt` | Numbers | CIDR block, VLAN ID, port range — Parakeet number-handling stress test |

## Recording workflow

1. **Add 5 ad-lib prompts of your own** (`prompt16_*.txt` … `prompt20_*.txt`). Speak something you'd actually dictate that day, then write what you said into the matching `.txt`. Scripted-only corpora make Parakeet look better than it is.
2. **Record each prompt as a 16 kHz mono 16-bit WAV** with the same base name. Two easy options:
   - Windows Voice Recorder → Save as → export MP3 → convert with `ffmpeg -i in.m4a -ar 16000 -ac 1 -sample_fmt s16 prompt01_claudecode_dependabot.wav`.
   - `sounddevice` REPL: `python -c "import sounddevice as sd, scipy.io.wavfile as w; d=sd.rec(int(15*16000), 16000, 1, dtype='int16'); sd.wait(); w.write('out.wav', 16000, d)"` (needs `scipy`; one-shot).
   - Or use the same mic you'll dictate with day-to-day so the acoustic profile matches production.
3. **Drop the WAVs next to the `.txt` files.** The compare harness looks for matching basenames.
4. **Run the harnesses:**
   ```powershell
   python scripts/bench.py --wav-dir ./samples --runs 5
   python scripts/compare_accuracy.py --wav-dir ./samples --out ./samples/accuracy.md
   ```

## What to read verbatim vs. naturally

Read each prompt as you would naturally say it — don't over-enunciate. If the text says "port eight thousand eighty", say it the same way you'd say it to a colleague; Parakeet's number handling is part of what we're measuring.

The `.txt` file is the **reference**: it's what you *intended* to say. Small disfluencies (ums, restarts) are fine — tag them as errors in the accuracy table later if Parakeet transcribes them literally and you'd rather they vanish.

## Checked in, or .gitignored?

WAV files are not in version control (see [.gitignore](../.gitignore)). The `.txt` sidecars are checked in because they're small and the reference set is worth pinning. Commit your ad-lib `prompt16_*.txt` etc. if you want them tracked.
