#!/usr/bin/env python3
"""
agent/demo.py — portfolio demo: SharpEdge across several matches, then an
aggregate track record. This is the story for the demo video: an autonomous
agent that flags sharp money in real time and keeps an auditable P&L.

  python -m agent.demo            # full run with LLM reads
  python -m agent.demo --fast     # no LLM (deterministic core only)
"""
from __future__ import annotations

import argparse

from .detector import SharpDetector
from .reason import explain
from .tracker import Tracker
from .simulator import stream

# (match, fixture_id, seed, steam_steps, winning_selection)
MATCHES = [
    ("Brazil vs Argentina", 1001, 42, (40, 85), "2"),
    ("France vs England",    1002, 7,  (30, 70, 95), "1"),
    ("Spain vs Germany",     1003, 19, (55,), "X"),
    ("Portugal vs Morocco",  1004, 88, (25, 60), "1"),
]


def run(use_llm: bool = True) -> None:
    tr = Tracker()
    per_match = []
    print("=" * 64)
    print(" SharpEdge — autonomous sharp-money agent · TxLINE World Cup feed")
    print("=" * 64)
    for match, fid, seed, steam, winner in MATCHES:
        det = SharpDetector(fixture_id=fid, match=match)
        local = Tracker()
        print(f"\n▶ {match}")
        for snap in stream(seed=seed, steps=120, steam_at=steam, winner=winner):
            for sig in det.update(snap["odds"], ts=snap["ts"]):
                tr.record(sig); local.record(sig)
                print(f"  🚨 {sig.kind:5} '{sig.selection}' Δ{sig.delta_p:+.3f} ({sig.z:+.1f}σ) @ {sig.odds_after}")
                if use_llm:
                    print(f"     🧠 {explain(sig)}")
        res = local.score(winner)
        per_match.append((match, res))
        print(f"  ⚽ FT '{winner}' → {res['hits']}/{res['signals_scored']} hits, {res['total_roi_units']:+.2f}u")

    tr.save()
    # portfolio aggregate
    tot_sig = sum(r["signals_scored"] for _, r in per_match)
    tot_hit = sum(r["hits"] for _, r in per_match)
    tot_roi = sum(r["total_roi_units"] for _, r in per_match)
    print("\n" + "=" * 64)
    print(" PORTFOLIO TRACK RECORD (auditable — out/signals.json)")
    print("=" * 64)
    print(f"  matches         : {len(MATCHES)}")
    print(f"  directional sigs: {tot_sig}")
    print(f"  hit rate        : {(tot_hit/tot_sig*100 if tot_sig else 0):.0f}%  ({tot_hit}/{tot_sig})")
    print(f"  total ROI       : {tot_roi:+.2f}u  ({(tot_roi/tot_sig if tot_sig else 0):+.2f}u/signal)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    a = ap.parse_args()
    run(use_llm=not a.fast)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
