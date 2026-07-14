"""
agent/alerts.py — SharpEdge's conviction alert stream (the pro-tool headline feature).

The $199/mo desks (OddsJam, Unabated, Action Network) sell one thing above all: a
real-time STEAM ALERT — a push the moment sharp money moves a line. SharpEdge emits the
same, but graded by our validated 0-100 steam-strength score and written to an append-only
JSONL feed a downstream consumer (a Telegram bot, a webhook, an execution agent) can tail.

Nothing here is fabricated: every alert is a real detector signal over real (or cached-real)
TxLINE odds. The projected edge shown is the BACKTESTED CLV for the signal's conviction tier
(reproducible via `python -m agent.backtest`), labeled as backtested — not a guarantee.

  python -m agent.alerts                     # scan cached real odds, print + write out/alerts.jsonl
  python -m agent.alerts --live              # tail the real devnet feed
  python -m agent.alerts --min-strength 80   # only high-conviction (STRONG) alerts
  python -m agent.alerts --webhook <url>     # also POST each alert as JSON
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

from .detector import SharpDetector, Signal

_HERE = Path(__file__).resolve().parent.parent
_JSONL = _HERE / "out" / "alerts.jsonl"

STRONG_TIER = 80.0        # matches agent.backtest STRENGTH_TIER
# backtested CLV per tier (from agent.backtest, n=400, default seed) — labeled, not promised
_TIER_CLV = {"STRONG": 9.8, "WEAK": 3.4}


def tier_of(strength: float) -> str:
    return "STRONG" if strength >= STRONG_TIER else "WEAK"


def build_alert(sig: Signal, match: str) -> dict:
    """Pure: turn a detector Signal into a structured, JSON-serializable alert."""
    side = {"1": "home", "X": "draw", "2": "away"}.get(sig.selection, sig.selection)
    team = match.split(" v ")[0] if sig.selection == "1" else (
        match.split(" v ")[-1] if sig.selection == "2" else "the draw")
    tier = tier_of(sig.strength)
    return {
        "ts": sig.ts,
        "fixture": sig.fixture_id,
        "match": match,
        "selection": sig.selection,
        "side": side,
        "team": team,
        "kind": sig.kind,                       # STEAM | DRIFT
        "z": sig.z,
        "delta_pp": round(sig.delta_p * 100, 2),
        "velocity_pp_min": round(sig.velocity * 100, 2),
        "strength": sig.strength,
        "tier": tier,
        "odds": sig.odds_after,
        "backtested_clv_pct": _TIER_CLV[tier],  # labeled: historical, not a guarantee
        "headline": (f"{'🚨' if tier == 'STRONG' else '⚠️'} {tier} steam — {team} "
                     f"({sig.z:+.1f}σ, conviction {sig.strength:.0f}/100) @ {sig.odds_after}"),
    }


class AlertStream:
    """Dedups alerts so the same fixture+selection fires once per crossing."""

    def __init__(self, min_strength: float = 0.0, jsonl_path: Path = _JSONL,
                 webhook: Optional[str] = None):
        self.min_strength = min_strength
        self.jsonl_path = jsonl_path
        self.webhook = webhook
        self._seen: set = set()
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    def push(self, sig: Signal, match: str) -> Optional[dict]:
        if sig.delta_p <= 0 or sig.strength < self.min_strength:
            return None
        key = (sig.fixture_id, sig.selection)
        if key in self._seen:
            return None
        self._seen.add(key)
        alert = build_alert(sig, match)
        with self.jsonl_path.open("a") as f:
            f.write(json.dumps(alert) + "\n")
        if self.webhook:
            self._post(alert)
        return alert

    def _post(self, alert: dict) -> None:
        try:
            import httpx
            httpx.post(self.webhook, json=alert, timeout=8)
        except Exception as e:                  # a down webhook must never break the stream
            print(f"  (webhook post failed: {e})")


# Same detection sensitivity the live dashboard uses, so alerts catch real pre-match
# money-flow steam (not just big in-play jumps). Conviction is graded by the STRENGTH
# score, not the fire-gate — a low-strength alert is still shown, just tiered WEAK.
_Z_THRESHOLD = 1.5
_MIN_ABS_MOVE = 0.005


def scan_series(series: List[dict], fixture_id: int, match: str,
                stream: AlertStream) -> List[dict]:
    """Run the detector over an odds series and collect the alerts it fires."""
    det = SharpDetector(fixture_id=fixture_id, match=match,
                        z_threshold=_Z_THRESHOLD, min_abs_move=_MIN_ABS_MOVE)
    out = []
    for pt in series:
        for sig in det.update(pt["odds"], ts=pt.get("ts")):
            a = stream.push(sig, match)
            if a:
                out.append(a)
    return out


def _cached_fixtures() -> List[dict]:
    cache = _HERE / "live_cache.json"
    data = json.loads(cache.read_text())
    out = []
    for f in data.get("fixtures", []):
        home, away = f.get("home"), f.get("away")
        name = f"{home} v {away}" if home and away else (f.get("name") or "fixture")
        out.append((f.get("id") or f.get("fixture_id"), name,
                    f.get("series") or f.get("odds_series") or []))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="tail the real devnet feed")
    ap.add_argument("--min-strength", type=float, default=0.0)
    ap.add_argument("--fixture", type=int)
    ap.add_argument("--webhook")
    a = ap.parse_args()

    stream = AlertStream(min_strength=a.min_strength, webhook=a.webhook)
    print("=" * 64)
    print(f" SharpEdge — conviction alert stream  (min strength {a.min_strength:.0f})")
    print(f" writing → {stream.jsonl_path}")
    print("=" * 64)

    fixtures = []
    if a.live:
        from txline import live_mainnet as L, live_feed as F
        L.set_network("devnet")
        for f in F.fixtures(72):
            if a.fixture and f["FixtureId"] != a.fixture:
                continue
            fixtures.append((f["FixtureId"], f"{f['Participant1']} v {f['Participant2']}",
                             F.odds_series(f["FixtureId"])))
    else:
        fixtures = [(fid, name, ser) for fid, name, ser in _cached_fixtures()
                    if not a.fixture or fid == a.fixture]

    total = 0
    for fid, name, ser in fixtures:
        alerts = scan_series(ser, fid, name, stream)
        for al in alerts:
            print(f"  {al['headline']}  [{name}]  backtested CLV {al['backtested_clv_pct']:+.1f}%")
        total += len(alerts)
    print("-" * 64)
    print(f" {total} conviction alert(s) fired → tail {stream.jsonl_path} to consume them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
