"""
agent/tracker.py — signal→outcome scoring (the "was it right?" layer).

Each sharp signal implies a directional read: money moving INTO a selection
(Δp>0) predicts that selection is MORE likely to win. We score every signal two ways:

  1. OUTCOME (did it win?) — when the match settles via the scores feed:
       - hit  = the sharp side (Δp>0 selection) actually won
       - roi  = P&L if you'd staked 1u on the sharp side at its odds when flagged
     Honest but noisy: a single match is one coin flip; edge only shows over volume.

  2. CLV — Closing Line Value — the metric professional betting desks actually use
     to prove edge *independently of results*. If the odds you caught keep shortening
     into the close, you consistently bought value before the market agreed. Beating
     the closing line is the strongest known predictor of long-run profit, and it
     needs no lucky outcomes — so it de-noises a demo that can't wait for 104 matches
     to settle. CLV% = (odds_when_flagged - closing_odds) / closing_odds, per signal.

This dual track record — outcome P&L plus CLV — is the core "production readiness"
story: it is exactly how a trading desk validates a signal.
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Deque

from .detector import Signal

_LOG = Path(__file__).resolve().parent.parent / "out" / "signals.jsonl"


def selection_won(result_selection: str, signal_selection: str) -> bool:
    return result_selection == signal_selection


@dataclass
class Scored:
    signal: Signal
    won: bool
    roi: float
    clv_pct: Optional[float] = None   # + = caught better-than-closing odds (beat the line)


@dataclass
class Tracker:
    # Bound memory to last 1000 signals to prevent OOM in 24/7 autonomous deployment
    signals: Deque[Signal] = field(default_factory=lambda: deque(maxlen=1000))

    def record(self, sig: Signal) -> None:
        self.signals.append(sig)
        self.save_single(sig) # Append to file immediately without full rewrite

    def save_single(self, sig: Signal) -> None:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        # Use JSONL (JSON Lines) for append-only fast disk IO
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(sig.to_dict()) + "\n")

    def save(self) -> None:
        pass # Deprecated in favor of save_single append-only IO

    def score(self, winning_selection: str,
              closing_odds: Optional[Dict[str, float]] = None) -> dict:
        """Score all money-IN (Δp>0) signals on outcome P&L and, if the closing line
        is supplied, on CLV (closing line value)."""
        directional = [s for s in self.signals if s.delta_p > 0]
        scored: List[Scored] = []
        for s in directional:
            won = selection_won(winning_selection, s.selection)
            roi = (s.odds_after - 1.0) if won else -1.0        # 1u on the sharp side
            clv = None
            if closing_odds and s.selection in closing_odds and closing_odds[s.selection] > 0:
                clv = (s.odds_after - closing_odds[s.selection]) / closing_odds[s.selection]
            scored.append(Scored(s, won, roi, clv))
        n = len(scored)
        hits = sum(1 for x in scored if x.won)
        pnl = sum(x.roi for x in scored)
        clvs = [x.clv_pct for x in scored if x.clv_pct is not None]
        beat = sum(1 for c in clvs if c > 0)
        return {
            "signals_scored": n,
            "hits": hits,
            "hit_rate": round(hits / n, 3) if n else 0.0,
            "total_roi_units": round(pnl, 3),
            "roi_per_signal": round(pnl / n, 3) if n else 0.0,
            "winning_selection": winning_selection,
            # CLV block (present when a closing line was supplied)
            "clv_signals": len(clvs),
            "avg_clv_pct": round(sum(clvs) / len(clvs) * 100, 2) if clvs else None,
            "beat_close": beat,
            "beat_close_rate": round(beat / len(clvs), 3) if clvs else None,
        }
