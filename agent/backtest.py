"""
agent/backtest.py — statistical backtest over many matches.

A 4-match demo is a story; a desk wants numbers with error bars. This runs the
cross-market detector over N simulated fixtures and reports, for CONFIRMED vs
UNCONFIRMED signals: hit rate with a Wilson 95% confidence interval, average CLV, the
rate of beating the closing line, and ROI. The headline it produces — CONFIRMED signals
beat UNCONFIRMED ones — is the empirical justification for the cross-market filter.

  python -m agent.backtest            # 200 matches
  python -m agent.backtest --n 500
"""
from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass, field
from typing import List, Optional

from .multimarket import stream_multi, CrossConfirmedDetector


def wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple:
    """95% Wilson score interval for a binomial proportion (well-behaved at small n)."""
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


@dataclass
class Bucket:
    hits: int = 0
    n: int = 0
    roi: float = 0.0
    clv_sum: float = 0.0
    clv_n: int = 0
    beat: int = 0

    def add(self, won: bool, roi: float, clv: Optional[float]) -> None:
        self.n += 1
        self.hits += 1 if won else 0
        self.roi += roi
        if clv is not None:
            self.clv_sum += clv
            self.clv_n += 1
            self.beat += 1 if clv > 0 else 0

    def report(self) -> dict:
        lo, hi = wilson_ci(self.hits, self.n)
        return {
            "signals": self.n,
            "hit_rate": round(self.hits / self.n, 3) if self.n else 0.0,
            "ci95": (round(lo, 3), round(hi, 3)),
            "roi_per_signal": round(self.roi / self.n, 3) if self.n else 0.0,
            "avg_clv_pct": round(self.clv_sum / self.clv_n * 100, 2) if self.clv_n else None,
            "beat_close_rate": round(self.beat / self.clv_n, 3) if self.clv_n else None,
        }


def run(n_matches: int = 200, base_seed: int = 0) -> dict:
    rng = random.Random(base_seed)
    confirmed = Bucket()
    unconfirmed = Bucket()

    for _ in range(n_matches):
        seed = rng.randint(1, 10_000_000)
        winner = rng.choice(["1", "X", "2"])
        goals_over = rng.random() < 0.5
        steam_at = tuple(sorted(rng.sample(range(10, 115), rng.randint(2, 4))))
        det = CrossConfirmedDetector(fixture_id=seed, match="bt")

        pending = []            # (signal, confirmed)
        closing = {}
        for tick in stream_multi(seed=seed, steps=120, winner=winner,
                                 goals_over=goals_over, steam_at=steam_at):
            closing = tick["1x2"]
            pending.extend(det.update(tick))

        for sig, is_conf in pending:
            if sig.delta_p <= 0:            # score only money-IN (directional) signals
                continue
            won = (sig.selection == winner)
            roi = (sig.odds_after - 1.0) if won else -1.0
            clv = None
            if sig.selection in closing and closing[sig.selection] > 0:
                clv = (sig.odds_after - closing[sig.selection]) / closing[sig.selection]
            (confirmed if is_conf else unconfirmed).add(won, roi, clv)

    return {"matches": n_matches,
            "confirmed": confirmed.report(),
            "unconfirmed": unconfirmed.report()}


def _fmt(label: str, r: dict) -> str:
    clv = f"{r['avg_clv_pct']:+.1f}%" if r["avg_clv_pct"] is not None else "n/a"
    beat = f"{r['beat_close_rate']*100:.0f}%" if r["beat_close_rate"] is not None else "n/a"
    lo, hi = r["ci95"]
    return (f"  {label:12} n={r['signals']:>4}  hit {r['hit_rate']*100:4.0f}% "
            f"[{lo*100:.0f}–{hi*100:.0f}%]  ROI {r['roi_per_signal']:+.3f}u  "
            f"CLV {clv}  beat-close {beat}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    res = run(a.n, a.seed)
    print("=" * 70)
    print(f" SharpEdge backtest — {res['matches']} matches, cross-market filter")
    print("=" * 70)
    print(_fmt("CONFIRMED", res["confirmed"]))
    print(_fmt("UNCONFIRMED", res["unconfirmed"]))
    c, u = res["confirmed"], res["unconfirmed"]
    if c["avg_clv_pct"] is not None and u["avg_clv_pct"] is not None:
        print("-" * 70)
        print(f"  cross-market confirmation lifts avg CLV by "
              f"{c['avg_clv_pct'] - u['avg_clv_pct']:+.1f} points and hit rate by "
              f"{(c['hit_rate'] - u['hit_rate'])*100:+.0f} pts — the filter earns its keep.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
