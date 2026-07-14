"""
tests/test_alerts.py — the conviction alert stream builds correct, deduped alerts
from real detector signals. Hermetic (no network, temp JSONL).

Run:  python -m pytest tests/test_alerts.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.alerts import build_alert, tier_of, AlertStream, STRONG_TIER
from agent.detector import Signal


def _sig(sel="1", strength=90.0, dp=0.05, fixture=1):
    return Signal(ts=100.0, fixture_id=fixture, match="France v Spain", selection=sel,
                  delta_p=dp, z=4.2, kind="STEAM", prob_before=0.5, prob_after=0.55,
                  odds_after=1.8, velocity=0.05, strength=strength)


def test_tier_split():
    assert tier_of(STRONG_TIER) == "STRONG"
    assert tier_of(STRONG_TIER - 0.1) == "WEAK"


def test_build_alert_maps_team_and_tier():
    a = build_alert(_sig(sel="1", strength=90), "France v Spain")
    assert a["team"] == "France" and a["side"] == "home"
    assert a["tier"] == "STRONG" and a["strength"] == 90
    assert a["backtested_clv_pct"] > 0            # labeled backtested edge present
    a2 = build_alert(_sig(sel="2", strength=50), "France v Spain")
    assert a2["team"] == "Spain" and a2["tier"] == "WEAK"


def test_stream_dedups_and_filters_and_persists():
    tmp = Path(tempfile.mkdtemp()) / "alerts.jsonl"
    s = AlertStream(min_strength=80.0, jsonl_path=tmp)
    # below threshold -> no alert
    assert s.push(_sig(strength=70), "France v Spain") is None
    # first strong -> fires
    assert s.push(_sig(sel="1", strength=90), "France v Spain") is not None
    # same fixture+selection again -> deduped
    assert s.push(_sig(sel="1", strength=95), "France v Spain") is None
    # non-directional (delta_p<=0) -> ignored
    assert s.push(_sig(sel="2", strength=90, dp=-0.02), "France v Spain") is None
    # persisted exactly one line
    lines = [l for l in tmp.read_text().splitlines() if l.strip()]
    assert len(lines) == 1 and json.loads(lines[0])["team"] == "France"


if __name__ == "__main__":
    test_tier_split()
    test_build_alert_maps_team_and_tier()
    test_stream_dedups_and_filters_and_persists()
    print("alert tests passed ✓")
