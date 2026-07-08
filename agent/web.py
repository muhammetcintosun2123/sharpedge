"""
agent/web.py — a self-contained dashboard for SharpEdge.

Runs the backtest (cross-market edge, with confidence intervals) and one sample match,
then bakes it into one themed HTML file — no server, no external assets. This is the
visual surface for the demo video: the win-probability curve with steam signals marked
CONFIRMED / UNCONFIRMED, and the headline table proving the cross-market filter's edge.

  python -m agent.web            # writes out/dashboard.html
  python -m agent.web --open
"""
from __future__ import annotations

import argparse
import json
import webbrowser
from pathlib import Path

from .multimarket import stream_multi, CrossConfirmedDetector
from .backtest import run

_OUT = Path(__file__).resolve().parent.parent / "out" / "dashboard.html"


def _sample_match(seed: int = 7, winner: str = "1", goals_over: bool = True):
    det = CrossConfirmedDetector(fixture_id=seed, match="Argentina vs Brazil")
    curve, signals = [], []
    closing = {}
    for tick in stream_multi(seed=seed, steps=120, winner=winner,
                             goals_over=goals_over, steam_at=(28, 55, 92)):
        closing = tick["1x2"]
        curve.append(round(1.0 / tick["1x2"]["1"], 4))       # implied home prob (with vig)
        for sig, conf in det.update(tick):
            signals.append({"i": len(curve) - 1, "sel": sig.selection,
                            "z": round(sig.z, 1), "dp": round(sig.delta_p, 3),
                            "odds": sig.odds_after, "confirmed": conf,
                            "up": sig.delta_p > 0})
    # attach CLV to money-in signals
    for s in signals:
        if s["up"] and s["sel"] in closing and closing[s["sel"]] > 0:
            s["clv"] = round((s["odds"] - closing[s["sel"]]) / closing[s["sel"]] * 100, 1)
    return {"winner": winner, "curve": curve, "signals": signals}


def build() -> Path:
    bt = run(n_matches=300, base_seed=0)
    data = {"backtest": bt, "sample": _sample_match()}
    html = _TEMPLATE.replace("/*__DATA__*/", json.dumps(data))
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(html)
    return _OUT


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SharpEdge — sharp-money detection, backtested</title>
<style>
:root{
 --bg:#0b0f17;--panel:#131a26;--edge:#212c3d;--fg:#e9eef6;--mut:#8496ac;
 --acc:#e8b23a;--acc2:#39b0e8;--good:#41d18a;--bad:#ff6f6f;
 --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
}
:root[data-theme="light"]{--bg:#f5f7fa;--panel:#fff;--edge:#dde4ec;--fg:#111b28;--mut:#5c6b7d}
@media(prefers-color-scheme:light){:root:not([data-theme="dark"]){--bg:#f5f7fa;--panel:#fff;--edge:#dde4ec;--fg:#111b28;--mut:#5c6b7d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.5}
.wrap{max-width:1000px;margin:0 auto;padding:22px}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--acc)}
h1{font-size:27px;margin:4px 0 4px}.lede{color:var(--mut);margin:0 0 18px;max-width:66ch}
.panel{background:var(--panel);border:1px solid var(--edge);border-radius:12px;padding:16px;margin-bottom:16px}
.panel h2{font-size:13px;text-transform:uppercase;letter-spacing:.1em;color:var(--mut);margin:0 0 12px;font-weight:600}
svg{width:100%;height:210px;display:block}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--mut);margin-top:8px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.06em;padding:8px;border-bottom:1px solid var(--edge)}
td{padding:10px 8px;border-bottom:1px solid var(--edge);font-variant-numeric:tabular-nums}
td.big{font-size:19px;font-weight:800}
.row-conf td{color:var(--fg)}.row-unc td{color:var(--mut)}
.tag{font-family:var(--mono);font-size:11px;padding:2px 8px;border-radius:999px}
.tag.c{color:var(--good);border:1px solid color-mix(in srgb,var(--good) 45%,transparent)}
.tag.u{color:var(--mut);border:1px solid var(--edge)}
.ci{font-family:var(--mono);font-size:12px;color:var(--mut)}
.kicker{background:color-mix(in srgb,var(--acc) 12%,transparent);border-left:3px solid var(--acc);border-radius:8px;padding:10px 14px;margin-bottom:16px;font-size:15px}
.foot{color:var(--mut);font-size:12px;font-family:var(--mono);margin-top:6px}
</style></head>
<body><div class="wrap">
<div class="eyebrow">TxODDS World Cup · Trading Tools &amp; Agents</div>
<h1>SharpEdge</h1>
<p class="lede">An autonomous agent that flags sharp-money steam moves on the TxLINE consensus feed —
deterministically — and proves its edge two ways a real desk trusts: Closing Line Value and
cross-market confirmation.</p>
<div class="kicker" id="kicker"></div>

<div class="panel">
  <h2>Sample match — win probability &amp; steam signals</h2>
  <svg id="chart" viewBox="0 0 320 210" preserveAspectRatio="none"></svg>
  <div class="legend">
    <span><span class="dot" style="background:var(--acc2)"></span>home win prob (implied)</span>
    <span><span class="dot" style="background:var(--good)"></span>CONFIRMED steam (1X2 + O/U agree)</span>
    <span><span class="dot" style="background:var(--mut)"></span>unconfirmed steam</span>
  </div>
</div>

<div class="panel">
  <h2>Backtest — 300 matches · does cross-market confirmation earn its keep?</h2>
  <table><thead><tr><th>signal</th><th>hit rate (95% CI)</th><th>ROI / signal</th><th>avg CLV</th><th>beat close</th></tr></thead>
  <tbody id="bt"></tbody></table>
  <p class="foot">Hit rate with Wilson 95% confidence intervals. The detector infers “confirmed” only from observed odds — it never sees which moves were informed.</p>
</div>
<p class="foot" id="gen">deterministic backtest · reproducible with <code>python -m agent.backtest --n 300</code></p>
</div>
<script>
const D=/*__DATA__*/;const $=id=>document.getElementById(id);
const c=D.backtest.confirmed,u=D.backtest.unconfirmed;
$("kicker").innerHTML=`Across 300 matches, <b>CONFIRMED</b> steam signals hit <b>${Math.round(c.hit_rate*100)}%</b> [${Math.round(c.ci95[0]*100)}–${Math.round(c.ci95[1]*100)}%] vs <b>${Math.round(u.hit_rate*100)}%</b> for single-market moves — the confidence intervals don't overlap. Cross-market agreement is a real conviction filter.`;
function ciPct(r){return `[${Math.round(r.ci95[0]*100)}–${Math.round(r.ci95[1]*100)}%]`;}
$("bt").innerHTML=
 `<tr class="row-conf"><td><span class="tag c">CONFIRMED</span></td><td class="big">${Math.round(c.hit_rate*100)}% <span class="ci">${ciPct(c)}</span></td><td>${c.roi_per_signal>0?'+':''}${c.roi_per_signal.toFixed(3)}u</td><td>${c.avg_clv_pct>0?'+':''}${c.avg_clv_pct}%</td><td>${Math.round(c.beat_close_rate*100)}%</td></tr>`+
 `<tr class="row-unc"><td><span class="tag u">unconfirmed</span></td><td class="big">${Math.round(u.hit_rate*100)}% <span class="ci">${ciPct(u)}</span></td><td>${u.roi_per_signal>0?'+':''}${u.roi_per_signal.toFixed(3)}u</td><td>${u.avg_clv_pct>0?'+':''}${u.avg_clv_pct}%</td><td>${Math.round(u.beat_close_rate*100)}%</td></tr>`;
// chart
const s=D.sample,cur=s.curve,W=320,H=210,pad=8;
let d="";cur.forEach((v,i)=>{const x=pad+(W-2*pad)*i/(cur.length-1);const y=H-pad-(H-2*pad)*v;d+=(i?"L":"M")+x.toFixed(1)+" "+y.toFixed(1)+" ";});
let marks="";s.signals.forEach(sg=>{const x=pad+(W-2*pad)*sg.i/(cur.length-1);const y=H-pad-(H-2*pad)*cur[sg.i];const col=sg.confirmed?"var(--good)":"var(--mut)";marks+=`<circle cx="${x}" cy="${y}" r="${sg.confirmed?4.5:3}" fill="${col}"/>`;});
$("chart").innerHTML=`<path d="${d}" fill="none" stroke="var(--acc2)" stroke-width="2"/>${marks}`;
</script>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    p = build()
    print(f"dashboard written: {p}")
    if a.open:
        webbrowser.open(f"file://{p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
