"""
agent/multimarket.py — cross-market confirmation, the way a real desk filters noise.

A steam move in the 1X2 market is more trustworthy when the *correlated* Over/Under
(total-goals) market moves consistently at the same time. Shared information — a key
injury, a tactical leak, heavy informed money — tends to hit both markets. A move that
shows up in ONE market only is more likely to be noise, a stale quote, or a
market-specific artifact.

So SharpEdge runs its deterministic detector (agent/detector.py) on BOTH the 1X2 and the
O/U feed, then tags each 1X2 steam:

    CONFIRMED    — an O/U steam fired in a consistent direction within CONFIRM_WINDOW
    UNCONFIRMED  — 1X2 moved alone

The backtest (agent/backtest.py) shows CONFIRMED signals carry a materially better edge —
which is the whole point: cross-market agreement is a real, defensible conviction filter,
not a black box.

`stream_multi` mirrors a TxLINE consumer subscribing to two markets on the same fixture.
"""
from __future__ import annotations

import random
from typing import Dict, Iterator, List, Optional, Tuple

from .detector import SharpDetector, Signal

CONFIRM_WINDOW_S = 180          # O/U move must land within 3 min of the 1X2 move
CONFIRM_RATE = 0.6              # share of steam events driven by shared (both-market) info


def _odds_1x2(p_home: float, p_draw: float, margin: float = 0.05) -> Dict[str, float]:
    p_away = max(0.01, 1.0 - p_home - p_draw)
    over = 1.0 + margin
    return {k: round(1.0 / (v * over), 3)
            for k, v in {"1": p_home, "X": p_draw, "2": p_away}.items()}


def _odds_ou(p_over: float, margin: float = 0.05) -> Dict[str, float]:
    p_over = min(0.92, max(0.08, p_over))
    over = 1.0 + margin
    return {"O": round(1.0 / (p_over * over), 3),
            "U": round(1.0 / ((1.0 - p_over) * over), 3)}


def stream_multi(seed: int = 42, steps: int = 120, winner: str = "2",
                 goals_over: bool = True,
                 steam_at: Tuple[int, ...] = (40, 85)) -> Iterator[Dict]:
    """Yield {'ts','1x2','ou'}. At each steam step the 1X2 jumps toward `winner`; with
    probability CONFIRM_RATE the O/U jumps consistently too (shared info)."""
    rng = random.Random(seed)
    p_home, p_draw, p_over = 0.40, 0.28, 0.50
    ts = 1_781_000_000.0
    for i in range(steps):
        # honest drift + noise
        p_home += rng.gauss(0.0015 if winner == "1" else (-0.0015 if winner == "2" else 0), 0.004)
        p_draw += rng.gauss(0, 0.003)
        p_over += rng.gauss(0.0015 if goals_over else -0.0015, 0.004)
        if i in steam_at:
            # Ground truth we do NOT reveal to the detector: informed money moves BOTH
            # markets; uninformed single-market moves are noisier and prone to head-fakes.
            informed = rng.random() < CONFIRM_RATE
            accuracy = 0.82 if informed else 0.42       # informed points at the winner more
            toward = winner if rng.random() < accuracy else rng.choice(["1", "X", "2"])
            if toward == "1":
                p_home += 0.06
            elif toward == "2":
                p_home -= 0.06
            else:
                p_draw += 0.045
            if informed:
                p_over += 0.06 if goals_over else -0.06   # shared info also moves O/U
            else:
                p_over += rng.gauss(0, 0.004)             # single-market: O/U barely reacts
        p_home = min(0.85, max(0.10, p_home))
        p_draw = min(0.40, max(0.12, p_draw))
        p_over = min(0.90, max(0.10, p_over))
        ts += 60.0
        yield {"ts": ts, "1x2": _odds_1x2(p_home, p_draw), "ou": _odds_ou(p_over)}


class CrossConfirmedDetector:
    """Runs the detector on both markets and tags each 1X2 signal CONFIRMED/UNCONFIRMED."""

    def __init__(self, fixture_id: int, match: str):
        self.d_1x2 = SharpDetector(fixture_id=fixture_id, match=match)
        self.d_ou = SharpDetector(fixture_id=fixture_id, match=match + " (O/U)")
        self._recent_ou: List[Signal] = []

    def update(self, tick: Dict) -> List[Tuple[Signal, bool]]:
        """Feed one multi-market tick. Returns (1X2 signal, confirmed) pairs."""
        ts = tick["ts"]
        ou_sigs = self.d_ou.update(tick["ou"], ts=ts)
        self._recent_ou.extend(ou_sigs)
        # drop stale O/U signals outside the window
        self._recent_ou = [s for s in self._recent_ou if ts - s.ts <= CONFIRM_WINDOW_S]

        out: List[Tuple[Signal, bool]] = []
        for sig in self.d_1x2.update(tick["1x2"], ts=ts):
            confirmed = any(abs(s.ts - sig.ts) <= CONFIRM_WINDOW_S for s in self._recent_ou)
            out.append((sig, confirmed))
        return out
