"""
agent/live.py — SharpEdge on the REAL TxLINE feed (no simulator).

Pulls the actual de-margined 1X2 odds history for real World Cup fixtures off the live
devnet feed and runs the exact same deterministic detector (agent/detector.py) over it.
Pre-match World Cup markets are efficient, so the STEAM gate (an in-play phenomenon)
stays honestly quiet; what's real and visible now is the pre-match money-flow drift —
which selection the market is steadily shortening. When matches kick off, the same
detector catches in-play steam.

Prereq: a live api token — `python -m txline.live_mainnet --network devnet --subscribe`.

  python -m agent.live                       # scan all live World Cup fixtures
  python -m agent.live --fixture 18209181    # one fixture
"""
from __future__ import annotations

import argparse

from .detector import SharpDetector, implied_probs
from .tracker import Tracker
from txline import live_mainnet as L
from txline import live_feed as F

_LABEL = {"1": "home", "X": "draw", "2": "away"}


def run_fixture(fixture_id: int, name: str) -> dict:
    series = F.odds_series(fixture_id)
    if len(series) < 10:
        print(f"  {name}: only {len(series)} odds points — skipping")
        return {}

    # the real detector over the real series
    det = SharpDetector(fixture_id=fixture_id, match=name)
    tr = Tracker()
    for pt in series:
        for sig in det.update(pt["odds"], ts=pt["ts"]):
            tr.record(sig)
    n_steam = sum(1 for s in tr.signals if s.kind == "STEAM")

    # real money-flow drift: de-vigged fair prob at open vs latest
    p_open = implied_probs(series[0]["odds"])
    p_now = implied_probs(series[-1]["odds"])
    drifts = {k: (p_now.get(k, 0) - p_open.get(k, 0)) for k in ("1", "X", "2")}
    into = max(drifts, key=lambda k: drifts[k])
    parts = name.split(" v ")
    who = parts[0] if into == "1" else (parts[-1] if into == "2" else "the draw")

    print(f"\n▶ {name}  ({len(series)} real odds updates)")
    print(f"  open  1/X/2 fair: {p_open['1']:.0%} / {p_open['X']:.0%} / {p_open['2']:.0%}")
    print(f"  now   1/X/2 fair: {p_now['1']:.0%} / {p_now['X']:.0%} / {p_now['2']:.0%}")
    if drifts[into] > 0.003:
        print(f"  💸 pre-match money flowing into {who} "
              f"({_LABEL[into]}, +{drifts[into]*100:.1f}pp de-vigged)")
    if n_steam:
        for s in [x for x in tr.signals if x.kind == "STEAM"][:5]:
            print(f"  🚨 STEAM '{s.selection}' Δ{s.delta_p:+.3f} ({s.z:+.1f}σ) @ {s.odds_after}")
    else:
        print("  · no in-play STEAM (market efficient pre-match; the STEAM gate fires on "
              "the larger in-play moves once the match kicks off)")
    return {"fixture": fixture_id, "name": name, "points": len(series),
            "steam": n_steam, "into": _LABEL[into], "drift_pp": round(drifts[into] * 100, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", choices=["mainnet", "devnet"], default="devnet")
    ap.add_argument("--fixture", type=int)
    a = ap.parse_args()
    L.set_network(a.network)

    print("=" * 64)
    print(" SharpEdge — LIVE on the real TxLINE World Cup feed")
    print("=" * 64)
    if a.fixture:
        run_fixture(a.fixture, f"fixture {a.fixture}")
        return 0
    for f in F.fixtures(72):
        run_fixture(f["FixtureId"], f"{f['Participant1']} v {f['Participant2']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
