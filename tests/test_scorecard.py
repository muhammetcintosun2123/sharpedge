"""
tests/test_scorecard.py — the live Desk Scorecard scores fired signals against the
closing line and splits them by the validated steam-strength tier. Pure CLV math,
no winner required (CLV is the leading edge indicator).

Run:  python -m pytest tests/test_scorecard.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import serve
from agent.detector import Signal


def _sig(sel, odds_after, strength):
    return Signal(ts=0, fixture_id=1, match="m", selection=sel, delta_p=0.03, z=4.0,
                  kind="STEAM", prob_before=0.5, prob_after=0.53, odds_after=odds_after,
                  velocity=0.03, strength=strength)


def test_scorecard_tiers_and_clv():
    sigs = [_sig("1", 2.0, 90), _sig("1", 1.9, 85), _sig("2", 3.0, 40)]
    closing = {"1": 1.7, "2": 3.1}
    sc = serve._session_scorecard(sigs, closing)
    assert sc["all"]["signals"] == 3
    assert sc["strong"]["signals"] == 2 and sc["weak"]["signals"] == 1
    # entered at 2.0/1.9, closed at 1.7 -> beat the close (positive CLV)
    assert sc["strong"]["avg_clv_pct"] > 0 and sc["strong"]["beat_close_rate"] == 1.0
    # entered at 3.0, closed at 3.1 -> worse than close (negative CLV)
    assert sc["weak"]["avg_clv_pct"] < 0
    assert 0.0 <= sc["avg_conviction"] <= 100.0


def test_scorecard_empty_is_safe():
    sc = serve._session_scorecard([], {"1": 2.0})
    assert sc["all"]["signals"] == 0
    assert sc["all"]["avg_clv_pct"] is None
    assert sc["avg_conviction"] == 0.0


if __name__ == "__main__":
    test_scorecard_tiers_and_clv()
    test_scorecard_empty_is_safe()
    print("scorecard tests passed ✓")
