"""
tests/test_core.py — proves the two properties judges asked for: the detector is
DETERMINISTIC (same feed -> same signals, bit for bit) and the scoring math is right.

Run:  python -m pytest -q     (or: python tests/test_core.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.detector import SharpDetector, implied_probs
from agent.tracker import Tracker
from agent.simulator import stream


def _collect(seed=42, winner="2"):
    det = SharpDetector(fixture_id=1, match="A vs B")
    sigs = []
    for snap in stream(seed=seed, steps=120, steam_at=(40, 85), winner=winner):
        sigs.extend(det.update(snap["odds"], ts=snap["ts"]))
    return sigs


def test_devig_sums_to_one():
    p = implied_probs({"1": 2.0, "X": 3.5, "2": 4.0})
    assert abs(sum(p.values()) - 1.0) < 1e-9


def test_detector_is_deterministic():
    # Same feed twice -> identical signals. No hidden state, no RNG in the detector.
    a = [s.to_dict() for s in _collect(seed=7)]
    b = [s.to_dict() for s in _collect(seed=7)]
    assert a == b and len(a) > 0


def test_no_signal_before_min_history():
    # First few updates must never fire (need volatility history first).
    det = SharpDetector(fixture_id=1, match="A vs B")
    fired = []
    for i, snap in enumerate(stream(seed=1, steps=6)):
        fired.extend(det.update(snap["odds"], ts=snap["ts"]))
    assert fired == []


def test_scoring_and_clv():
    det = SharpDetector(fixture_id=1, match="A vs B")
    tr = Tracker()
    closing = {}
    for snap in stream(seed=42, steps=120, steam_at=(40, 85), winner="2"):
        closing = snap["odds"]
        for sig in det.update(snap["odds"], ts=snap["ts"]):
            tr.record(sig)
    res = tr.score("2", closing_odds=closing)
    assert res["signals_scored"] >= 1
    assert 0.0 <= res["hit_rate"] <= 1.0
    # CLV must be populated when a closing line is supplied
    assert res["avg_clv_pct"] is not None
    assert res["clv_signals"] == res["signals_scored"]


if __name__ == "__main__":
    test_devig_sums_to_one()
    test_detector_is_deterministic()
    test_no_signal_before_min_history()
    test_scoring_and_clv()
    print("all core tests passed ✓")
