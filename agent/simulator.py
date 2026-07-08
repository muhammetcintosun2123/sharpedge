"""
agent/simulator.py — outcome-aware World-Cup 1X2 odds stream for dev & demo.

Models the real phenomenon the agent exploits: *sharp (informed) money has a modest
edge*. Each match has a true winner; the consensus fair-probability drifts and jumps
(steam moves) predominantly TOWARD that winner as information arrives — but with
realistic noise, so sharp moves are right only ~2/3 of the time (as in real markets).
The agent that reliably catches these steam moves therefore shows a realistic
positive-but-not-magical edge — the honest story for the demo. Output shape mirrors
the TxLINE odds consumer: {"1": home_odds, "X": draw_odds, "2": away_odds}.
"""
from __future__ import annotations

import random
from typing import Dict, Iterator, Tuple

SHARP_ACCURACY = 0.68   # a steam move points at the eventual winner ~68% of the time


def _odds_from_probs(p_home: float, p_draw: float, margin: float = 0.05) -> Dict[str, float]:
    p_away = max(0.01, 1.0 - p_home - p_draw)
    probs = {"1": p_home, "X": p_draw, "2": p_away}
    over = 1.0 + margin
    return {k: round(1.0 / (v * over), 3) for k, v in probs.items()}


def _nudge(p_home: float, p_draw: float, toward: str, size: float):
    """Shift fair probability toward selection `toward` by ~size."""
    if toward == "1":
        p_home += size
    elif toward == "2":
        p_home -= size
    else:  # draw
        p_draw += size * 0.7
        p_home -= size * 0.3
    return p_home, p_draw


def stream(seed: int = 42, steps: int = 120, steam_at: Tuple[int, ...] = (40, 85),
           winner: str = "2") -> Iterator[Dict]:
    """Yield {'ts','odds','true_home_p'}. Steam moves point at `winner` ~SHARP_ACCURACY."""
    rng = random.Random(seed)
    p_home, p_draw = 0.40, 0.28
    ts = 1_781_000_000.0
    for i in range(steps):
        # small honest drift toward the winner (info arriving) + micro-noise
        p_home, p_draw = _nudge(p_home, p_draw, winner, rng.gauss(0.0015, 0.0015))
        p_home += rng.gauss(0, 0.004)
        p_draw += rng.gauss(0, 0.003)
        if i in steam_at:
            # sharp jump: mostly toward the winner, sometimes a head-fake
            toward = winner if rng.random() < SHARP_ACCURACY else rng.choice(["1", "X", "2"])
            p_home, p_draw = _nudge(p_home, p_draw, toward, 0.06)
        p_home = min(0.85, max(0.10, p_home))
        p_draw = min(0.40, max(0.12, p_draw))
        ts += 60.0
        yield {"ts": ts, "odds": _odds_from_probs(p_home, p_draw), "true_home_p": round(p_home, 4)}
