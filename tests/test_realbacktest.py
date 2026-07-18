"""
tests/test_realbacktest.py — the real-data backtest's honesty invariants.
Run: python -m pytest tests/test_realbacktest.py -q

Hermetic: no network. These pin the METHOD (which is where the earlier claim went wrong),
not the numbers — the numbers must come from the live feed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import realbacktest as R


def test_merge_forward_fills_and_never_invents():
    x12 = [{"ts": 10, "odds": {"1": 2.0}}, {"ts": 20, "odds": {"1": 2.1}},
           {"ts": 30, "odds": {"1": 2.2}}]
    ou = [{"ts": 5, "odds": {"over": 1.9, "under": 1.9}},
          {"ts": 25, "odds": {"over": 1.8, "under": 2.0}}]
    out = R._merge(x12, ou)
    assert len(out) == 3
    # each 1X2 tick carries the most recent O/U quote at or before it — never a future one
    assert out[0]["ou"]["over"] == 1.9
    assert out[1]["ou"]["over"] == 1.9      # 25 hasn't landed yet at ts=20
    assert out[2]["ou"]["over"] == 1.8
    # no interpolated/invented prices: every ou value came from the source series
    seen = {1.9, 1.8}
    assert all(t["ou"]["over"] in seen for t in out)


def test_merge_drops_ticks_before_any_ou_quote():
    # a 1X2 tick with no O/U quote yet cannot be confirmed either way -> excluded,
    # rather than pretending the correlated market said something
    x12 = [{"ts": 1, "odds": {"1": 2.0}}, {"ts": 9, "odds": {"1": 2.0}}]
    ou = [{"ts": 5, "odds": {"over": 1.9, "under": 1.9}}]
    out = R._merge(x12, ou)
    assert [t["ts"] for t in out] == [9]


def test_stats_reports_ci_and_handles_empty():
    empty = R._stats([])
    assert empty["signals"] == 0 and empty["avg_clv_pct"] is None
    s = R._stats([0.10, -0.05, 0.20, 0.01])
    assert s["signals"] == 4
    assert s["beat_close_rate"] == 0.75          # 3 of 4 beat the close
    assert s["avg_clv_pct"] == 6.5               # mean of +10,-5,+20,+1 pct
    lo, hi = s["ci95"]
    assert 0.0 <= lo < hi <= 1.0                 # a real interval, always reported


def test_tier_matches_the_scores_documented_cutoff():
    assert R.STRENGTH_TIER == 80.0


def test_played_fixture_ids_are_real_and_unique():
    assert len(R.PLAYED_FIXTURES) == len(set(R.PLAYED_FIXTURES))
    assert all(isinstance(f, int) and f > 0 for f in R.PLAYED_FIXTURES)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
