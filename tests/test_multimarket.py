"""
tests/test_multimarket.py — the cross-market layer is deterministic and the confirmation
filter demonstrably separates informed signals from noise.
Run: python tests/test_multimarket.py  (or pytest -q)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.multimarket import stream_multi, CrossConfirmedDetector
from agent.backtest import run, wilson_ci


def test_stream_multi_deterministic():
    a = [(t["1x2"], t["ou"]) for t in stream_multi(seed=3)]
    b = [(t["1x2"], t["ou"]) for t in stream_multi(seed=3)]
    assert a == b and len(a) == 120


def test_detector_emits_confirmed_flags():
    det = CrossConfirmedDetector(1, "A vs B")
    flags = []
    for t in stream_multi(seed=42, winner="2", steam_at=(30, 60, 90)):
        flags.extend(c for _, c in det.update(t))
    assert len(flags) > 0
    assert all(isinstance(c, bool) for c in flags)


def test_wilson_ci_bounds():
    lo, hi = wilson_ci(8, 10)
    assert 0.0 <= lo <= 0.8 <= hi <= 1.0
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_confirmed_beats_unconfirmed():
    # over a decent sample, CONFIRMED signals must show a higher hit rate — the whole
    # justification for the cross-market filter. (Deterministic seed for reproducibility.)
    res = run(n_matches=200, base_seed=0)
    c, u = res["confirmed"], res["unconfirmed"]
    assert c["signals"] > 30 and u["signals"] > 30
    assert c["hit_rate"] > u["hit_rate"]
    # and the edge is large enough that the confidence intervals don't overlap
    assert c["ci95"][0] > u["ci95"][1]


if __name__ == "__main__":
    test_stream_multi_deterministic()
    test_detector_emits_confirmed_flags()
    test_wilson_ci_bounds()
    test_confirmed_beats_unconfirmed()
    print("all multimarket tests passed ✓")
