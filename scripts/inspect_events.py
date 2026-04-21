"""Read-only viewer for ``training_data/events.jsonl``.

Prints the most recent N entries in a compact, colourised form so you can
sanity-check what the daemon + the Claude Code hook have been recording.

Examples
--------
::

    python scripts/inspect_events.py               # last 20 entries, both kinds
    python scripts/inspect_events.py --tail 5      # last 5
    python scripts/inspect_events.py --kind dictation
    python scripts/inspect_events.py --kind submit
    python scripts/inspect_events.py --grep Dependabot
    python scripts/inspect_events.py --pairs       # align dictation → submit by time
    python scripts/inspect_events.py --stats       # counts, mean latencies, top fixup terms

Does not mutate the log. Safe to run while the daemon is active.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import datetime
from pathlib import Path

_DEFAULT_EVENTS = Path(__file__).resolve().parent.parent / "training_data" / "events.jsonl"


def _reconfigure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _load_events(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    records: list[dict] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"warn: line {line_no} is not valid JSON: {exc}", file=sys.stderr)
    return records


def _fmt_ts(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _truncate(text: str, width: int) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= width else text[: width - 1] + "…"


def _print_record(rec: dict, width: int = 100) -> None:
    ts = _fmt_ts(rec.get("ts", ""))
    kind = rec.get("kind", "?")
    if kind == "dictation":
        stages = rec.get("stages", {})
        total = sum(float(v) for v in stages.values())
        audio = rec.get("audio_ms", 0)
        hits = rec.get("fixup_hits", 0)
        raw = _truncate(rec.get("raw", ""), width)
        fixed = _truncate(rec.get("fixed", ""), width)
        print(f"[{ts}] DICT   audio={audio}ms total={total:.0f}ms hits={hits}")
        print(f"    raw   : {raw}")
        if rec.get("fixed") != rec.get("raw"):
            print(f"    fixed : {fixed}")
    elif kind == "submit":
        prompt = _truncate(rec.get("prompt", ""), width)
        cwd = rec.get("cwd") or "?"
        print(f"[{ts}] SUBMIT cwd={cwd}")
        print(f"    prompt: {prompt}")
    else:
        print(f"[{ts}] {kind.upper()} {rec}")


def _cmd_tail(records: list[dict], args: argparse.Namespace) -> None:
    filtered = [r for r in records if args.kind in (None, r.get("kind"))]
    if args.grep:
        needle = args.grep.lower()
        filtered = [
            r
            for r in filtered
            if any(
                needle in str(r.get(field, "")).lower()
                for field in ("raw", "fixed", "prompt")
            )
        ]
    for rec in filtered[-args.tail :]:
        _print_record(rec)


def _cmd_pairs(records: list[dict], args: argparse.Namespace) -> None:
    """Naive pairing: for each dictation, find the first submit within ``--window`` seconds."""
    dicts = [r for r in records if r.get("kind") == "dictation"]
    submits = [r for r in records if r.get("kind") == "submit"]

    def _parse(r: dict) -> datetime | None:
        try:
            return datetime.fromisoformat(r["ts"])
        except (KeyError, ValueError):
            return None

    window_sec = args.window
    for d in dicts[-args.tail :]:
        d_ts = _parse(d)
        if d_ts is None:
            continue
        paired: dict | None = None
        for s in submits:
            s_ts = _parse(s)
            if s_ts is None:
                continue
            delta = (s_ts - d_ts).total_seconds()
            if 0 <= delta <= window_sec:
                paired = s
                break
        ts = _fmt_ts(d.get("ts", ""))
        raw = _truncate(d.get("raw", ""), 90)
        fixed = _truncate(d.get("fixed", ""), 90)
        print(f"[{ts}]")
        print(f"    raw   : {raw}")
        print(f"    fixed : {fixed}")
        if paired is not None:
            gap = (_parse(paired) - d_ts).total_seconds()  # type: ignore[operator]
            submit = _truncate(paired.get("prompt", ""), 90)
            print(f"    submit: {submit}  (+{gap:.0f}s)")
        else:
            print(f"    submit: <no submit within {window_sec}s>")


def _cmd_stats(records: list[dict]) -> None:
    dicts = [r for r in records if r.get("kind") == "dictation"]
    submits = [r for r in records if r.get("kind") == "submit"]
    print(f"dictation events : {len(dicts)}")
    print(f"submit events    : {len(submits)}")

    if dicts:
        stage_totals: dict[str, list[float]] = collections.defaultdict(list)
        audio_ms: list[int] = []
        hits_zero = 0
        for r in dicts:
            audio_ms.append(int(r.get("audio_ms", 0)))
            for k, v in (r.get("stages") or {}).items():
                stage_totals[k].append(float(v))
            if not r.get("fixup_hits"):
                hits_zero += 1

        def _mean(xs: list[float]) -> float:
            return sum(xs) / len(xs) if xs else 0.0

        print("")
        print(f"audio duration mean: {_mean(audio_ms) / 1000:.1f} s")
        print("stage latency means:")
        for stage, vals in sorted(stage_totals.items()):
            print(f"  {stage:>10s}: {_mean(vals):6.1f} ms  (n={len(vals)})")
        print(f"dictations with zero fixup hits: {hits_zero}/{len(dicts)}")


def main() -> int:
    _reconfigure_utf8()

    parser = argparse.ArgumentParser(
        prog="inspect_events",
        description="Tail / grep / pair-view the training_data/events.jsonl log.",
    )
    parser.add_argument(
        "--events-file",
        type=Path,
        default=_DEFAULT_EVENTS,
        help=f"Events file path (default: {_DEFAULT_EVENTS}).",
    )
    parser.add_argument("--tail", type=int, default=20, help="Show the last N matching entries (default: 20).")
    parser.add_argument("--kind", choices=["dictation", "submit"], help="Filter by event kind.")
    parser.add_argument("--grep", help="Case-insensitive substring filter over raw/fixed/prompt fields.")
    parser.add_argument(
        "--pairs",
        action="store_true",
        help="Pair dictation → submit events within --window seconds.",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=60.0,
        help="Pairing window in seconds (default: 60).",
    )
    parser.add_argument("--stats", action="store_true", help="Print counts and mean latencies, no records.")
    args = parser.parse_args()

    records = _load_events(args.events_file)
    if not records:
        print(f"No events in {args.events_file} yet.")
        return 0

    if args.stats:
        _cmd_stats(records)
        return 0
    if args.pairs:
        _cmd_pairs(records, args)
        return 0
    _cmd_tail(records, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
