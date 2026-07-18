"""
agent/realbacktest.py — the backtest on REAL TxLINE data, not a simulator.

`agent/backtest.py` validates the detector by Monte-Carlo: it generates fixtures where
informed money moves both markets (CONFIRM_RATE) and checks the detector recovers it.
That proves the detector can find a signal *that exists by construction* — it cannot tell
us the signal exists in the real market. This module answers that question, on the real
feed:

  * real 1X2 consensus series          (SuperOddsType 1X2_PARTICIPANT_RESULT)
  * real Over/Under 2.5 consensus series (OVERUNDER_PARTICIPANT_GOALS, line=2.5) — the
    genuinely correlated market the cross-market filter claims to use
  * CLV measured against the REAL closing line = the last price before the real kickoff
    (from the scores feed). Everything after kickoff is in-running and is excluded — a
    settled full-time price is not a "close".

No outcome/winner is needed: CLV is a pure function of the odds path, which is why it is
the honest edge metric for fixtures whose results we cannot prove.

  python -m agent.realbacktest                 # the known played World Cup fixtures
  python -m agent.realbacktest --json
"""
from __future__ import annotations

import argparse
import json
from typing import Dict, List, Optional, Tuple

from .backtest import wilson_ci
from .detector import SharpDetector
from .multimarket import CONFIRM_WINDOW_S

# Real World Cup fixtures with a full pre-match consensus history on the devnet feed.
# (The live snapshot only lists upcoming fixtures; played ones stay queryable by id.)
PLAYED_FIXTURES = [18209181, 18213979, 18218149, 18222446,
                   18179550, 18202783, 18237038, 17952170]

STRENGTH_TIER = 80.0


def _merge(x12: List[dict], ou: List[dict]) -> List[dict]:
    """Combine the two real series onto one timeline: at each 1X2 tick, carry the most
    recent O/U quote (forward-fill). No interpolation — we never invent a price."""
    out, j, cur = [], 0, None
    for p in x12:
        while j < len(ou) and ou[j]["ts"] <= p["ts"]:
            cur = ou[j]["odds"]
            j += 1
        if cur is not None:
            out.append({"ts": p["ts"], "1x2": p["odds"], "ou": cur})
    return out


def _stats(clvs: List[float]) -> dict:
    n = len(clvs)
    if not n:
        return {"signals": 0, "avg_clv_pct": None, "beat_close_rate": None, "ci95": None}
    beat = sum(1 for c in clvs if c > 0)
    lo, hi = wilson_ci(beat, n)
    return {
        "signals": n,
        "avg_clv_pct": round(sum(clvs) / n * 100, 2),
        "beat_close_rate": round(beat / n, 3),
        "ci95": (round(lo, 3), round(hi, 3)),
    }


def run(fixtures: Optional[List[int]] = None, line: str = "2.5") -> dict:
    from txline import live_mainnet as L, live_feed as F
    L.set_network("devnet")

    conf: List[float] = []
    unconf: List[float] = []
    strong: List[float] = []
    weak: List[float] = []
    per: List[dict] = []

    for fid in (fixtures or PLAYED_FIXTURES):
        x12 = F.odds_series(fid)
        ou = F.ou_series(fid, line=line)
        ko = F.kickoff_ts(fid)
        if ko:                                   # pre-match only; the close is at kickoff
            x12 = [p for p in x12 if p["ts"] <= ko]
            ou = [p for p in ou if p["ts"] <= ko]
        if len(x12) < 50 or len(ou) < 10:
            per.append({"fixture": fid, "skipped": "not enough real consensus history"})
            continue

        ticks = _merge(x12, ou)
        closing = x12[-1]["odds"]                # the real closing line
        d12 = SharpDetector(fixture_id=fid, match=str(fid), z_threshold=1.5, min_abs_move=0.005)
        dou = SharpDetector(fixture_id=fid, match=f"{fid} O/U", z_threshold=1.5, min_abs_move=0.005)
        recent_ou: List = []
        n_sig = n_conf = 0

        for t in ticks:
            ts = t["ts"]
            recent_ou.extend(dou.update(t["ou"], ts=ts) or [])
            recent_ou = [s for s in recent_ou if ts - s.ts <= CONFIRM_WINDOW_S]
            for sig in (d12.update(t["1x2"], ts=ts) or []):
                c = closing.get(sig.selection)
                if not c or c <= 0:
                    continue
                clv = (sig.odds_after - c) / c
                confirmed = any(abs(s.ts - sig.ts) <= CONFIRM_WINDOW_S for s in recent_ou)
                (conf if confirmed else unconf).append(clv)
                (strong if sig.strength >= STRENGTH_TIER else weak).append(clv)
                n_sig += 1
                n_conf += 1 if confirmed else 0

        per.append({"fixture": fid, "ticks_1x2": len(x12), "ticks_ou": len(ou),
                    "signals": n_sig, "confirmed": n_conf})

    return {
        "source": "REAL TxLINE devnet consensus — pre-match only, close = last price "
                  "before the real kickoff",
        "ou_line": line,
        "per_fixture": per,
        "confirmed": _stats(conf),
        "unconfirmed": _stats(unconf),
        "strong": _stats(strong),
        "weak": _stats(weak),
        "all": _stats(conf + unconf),
    }


def _fmt(name: str, s: dict) -> str:
    if not s["signals"]:
        return f"  {name:<14} no signals"
    ci = f"[{s['ci95'][0]*100:.0f}–{s['ci95'][1]*100:.0f}%]"
    return (f"  {name:<14} n={s['signals']:>4}  avg CLV {s['avg_clv_pct']:+6.2f}%  "
            f"beat-close {s['beat_close_rate']*100:>3.0f}% {ci}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--line", default="2.5", help="O/U total-goals line")
    a = ap.parse_args()
    out = run(line=a.line)
    if a.json:
        print(json.dumps(out, indent=2))
        return 0
    print("=" * 78)
    print(" SharpEdge — backtest on REAL TxLINE data (no simulator)")
    print("=" * 78)
    print(f" {out['source']}")
    print(f" Correlated market: real Over/Under {out['ou_line']} consensus\n")
    for p in out["per_fixture"]:
        if p.get("skipped"):
            print(f"  fixture {p['fixture']}: skipped — {p['skipped']}")
        else:
            print(f"  fixture {p['fixture']}: {p['ticks_1x2']:>5} 1X2 ticks · "
                  f"{p['ticks_ou']:>4} O/U ticks -> {p['signals']:>3} signals "
                  f"({p['confirmed']} confirmed)")
    print("\n CROSS-MARKET CONFIRMATION (the filter's claim):")
    print(_fmt("CONFIRMED", out["confirmed"]))
    print(_fmt("UNCONFIRMED", out["unconfirmed"]))
    print("\n STEAM-STRENGTH SCORE (the conviction claim, tier >= 80):")
    print(_fmt("STRONG", out["strong"]))
    print(_fmt("WEAK", out["weak"]))
    print("\n" + _fmt("ALL SIGNALS", out["all"]))
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
