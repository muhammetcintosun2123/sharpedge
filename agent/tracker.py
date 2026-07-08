"""
agent/tracker.py — signal→outcome scoring (the "was it right?" layer).

Each sharp signal implies a directional read: money moving INTO a selection
(Δp>0) predicts that selection is MORE likely to win. When the match settles
(via the scores feed), we score every signal:
  - hit   = the sharp side (Δp>0 selection) actually won
  - roi   = P&L if you'd staked 1u on the sharp side at its odds when flagged
This produces a live, auditable track record — the core of "production readiness".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .detector import Signal

_LOG = Path(__file__).resolve().parent.parent / "out" / "signals.json"


def selection_won(result_selection: str, signal_selection: str) -> bool:
    return result_selection == signal_selection


@dataclass
class Scored:
    signal: Signal
    won: bool
    roi: float


@dataclass
class Tracker:
    signals: List[Signal] = field(default_factory=list)

    def record(self, sig: Signal) -> None:
        self.signals.append(sig)

    def save(self) -> None:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        _LOG.write_text(json.dumps([s.to_dict() for s in self.signals], indent=1))

    def score(self, winning_selection: str) -> dict:
        """Score all money-IN (Δp>0) signals against the final result."""
        directional = [s for s in self.signals if s.delta_p > 0]
        scored: List[Scored] = []
        for s in directional:
            won = selection_won(winning_selection, s.selection)
            # stake 1u on the sharp side at the odds when flagged
            roi = (s.odds_after - 1.0) if won else -1.0
            scored.append(Scored(s, won, roi))
        n = len(scored)
        hits = sum(1 for x in scored if x.won)
        pnl = sum(x.roi for x in scored)
        return {
            "signals_scored": n,
            "hits": hits,
            "hit_rate": round(hits / n, 3) if n else 0.0,
            "total_roi_units": round(pnl, 3),
            "roi_per_signal": round(pnl / n, 3) if n else 0.0,
            "winning_selection": winning_selection,
        }
