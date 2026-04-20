"""Latency benchmark — runs the daemon pipeline against sample WAV files.

Reports p50 / p95 / p99 end-to-end latency plus per-stage breakdown
(VAD / encode / decode / paste). See handover §9b for the target SLO
(<500 ms end-to-end for a 15 s prompt on RTX 5080).

Deferred to a second implementation session after the MVP runs end-to-end.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("Deferred — see handover §9b.")


if __name__ == "__main__":
    main()
