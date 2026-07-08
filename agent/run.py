#!/usr/bin/env python3
"""
agent/run.py — SharpEdge autonomous loop (end to end).

Ingest odds (live TxLINE or the simulator) -> deterministic sharp detection ->
LLM one-line read -> record -> on settle, score the track record.

Fully automated: once started it needs no human input. This is the "autonomous
operation" the track asks for.

Usage:
  python -m agent.run --sim                 # demo on the simulator
  python -m agent.run --live --fixture <id> # live TxLINE feed (needs activated tokens)
"""
from __future__ import annotations

import argparse
import time

from .detector import SharpDetector
from .reason import explain
from .tracker import Tracker
from .simulator import stream


def run_sim(match: str = "Brazil vs Argentina", fixture_id: int = 1001,
            winning_selection: str = "2", explain_signals: bool = True,
            poll_s: float = 0.0) -> dict:
    """One fixture, start to settle. `poll_s` throttles the loop so you can watch it
    tick in real time (0 = as fast as possible, for tests/CI)."""
    det = SharpDetector(fixture_id=fixture_id, match=match)
    tr = Tracker()
    closing: dict = {}
    print(f"▶ SharpEdge daemon attached to: {match}  (fixture {fixture_id})\n")
    for snap in stream(steps=120, steam_at=(40, 85), winner=winning_selection):
        closing = snap["odds"]                     # newest snapshot = current/closing line
        for sig in det.update(snap["odds"], ts=snap["ts"]):
            tr.record(sig)
            line = f"🚨 {sig.kind:5} {sig.match} | '{sig.selection}' Δ{sig.delta_p:+.3f} ({sig.z:+.1f}σ) @ {sig.odds_after}"
            print(line)
            if explain_signals:
                print(f"   🧠 {explain(sig)}")
        if poll_s:
            time.sleep(poll_s)
    tr.save()
    print(f"\n⚽ Full time. Result: '{winning_selection}' wins. Scoring the sharp track record…\n")
    res = tr.score(winning_selection, closing_odds=closing)
    print(f"   signals scored : {res['signals_scored']}")
    print(f"   hit rate       : {res['hit_rate']*100:.0f}%  ({res['hits']}/{res['signals_scored']})")
    print(f"   ROI            : {res['total_roi_units']:+.2f}u  ({res['roi_per_signal']:+.2f}u/signal)")
    if res["avg_clv_pct"] is not None:
        print(f"   avg CLV        : {res['avg_clv_pct']:+.1f}%  (beat close {res['beat_close']}/{res['clv_signals']})")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--fixture", type=int)
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    if a.live:
        print("live mode: aktive edilmiş TxLINE token'ları gerekir (txline/subscribe.py). "
              "Şimdilik --sim kullan.")
        return 1
    run_sim(explain_signals=not a.no_llm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
