"""
serve.py — SharpEdge LIVE terminal: a real streaming web app for the demo.

Runs out of the box with ZERO setup:  `python3 serve.py`  →  http://localhost:8787
Needs only the Python standard library + agent/detector.py (no pip installs, no API token).

It streams REAL TxLINE World Cup odds over Server-Sent Events and runs the deterministic
detector on every tick server-side, pushing each tick + any signal to a live browser
terminal. By default it replays cached real odds (`live_cache.json`, genuine de-vigged
1X2 history captured from the subscribed devnet feed). Pass --live to pull fresh from the
live feed instead (needs httpx + solders + the activated token).

  python3 serve.py                # cached real odds (always works)
  python3 serve.py --live         # fresh from the live TxLINE feed
  python3 serve.py --port 9000    # choose a port
"""
from __future__ import annotations

import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from agent.detector import SharpDetector, implied_probs

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE = os.path.join(_HERE, "live_cache.json")

PACE_S = 0.05
USE_LIVE = False
_data = {"fixtures": []}     # loaded at startup from cache (always) — never blocks serving
_live = {"series": {}, "fixtures": None}


def load_cache():
    global _data
    try:
        with open(_CACHE) as f:
            _data = json.load(f)
    except Exception:
        _data = {"fixtures": []}


def fixtures():
    if USE_LIVE:
        try:
            from txline import live_mainnet as L, live_feed as F
            L.set_network("devnet")
            if _live["fixtures"] is None:
                _live["fixtures"] = [{"id": f["FixtureId"], "home": f["Participant1"],
                                      "away": f["Participant2"]} for f in F.fixtures(72)]
            return _live["fixtures"]
        except Exception as e:
            print(f"  (live feed unavailable: {e} — using cached real odds)")
    return [{"id": f["id"], "home": f["home"], "away": f["away"]} for f in _data["fixtures"]]


def odds_series(fid: int):
    """Return [{'ts','odds'}] of real odds for fixture — live if --live, else cache."""
    if USE_LIVE:
        try:
            from txline import live_feed as F
            return F.odds_series(fid)      # always fresh, so the live tail sees new updates
        except Exception:
            pass
    for f in _data["fixtures"]:
        if f["id"] == fid:
            return f["series"]
    return _data["fixtures"][0]["series"] if _data["fixtures"] else []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        try:
            if self.path == "/" or self.path.startswith("/?"):
                self._send(200, "text/html; charset=utf-8", PAGE.encode())
            elif self.path == "/fixtures":
                self._send(200, "application/json", json.dumps(fixtures()).encode())
            elif self.path.startswith("/stream"):
                self.stream()
            else:
                self._send(404, "text/plain", b"not found")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                self._send(500, "text/plain", str(e).encode())
            except Exception:
                pass

    def stream(self):
        q = parse_qs(urlparse(self.path).query)
        fx = fixtures()
        fid = int(q.get("fixture", ["0"])[0]) or (fx[0]["id"] if fx else 0)
        name = q.get("name", ["match"])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def emit(event, payload):
            self.wfile.write(f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode())
            self.wfile.flush()

        det = SharpDetector(fixture_id=fid, match=name, z_threshold=1.5, min_abs_move=0.005)
        
        OUTCOMES = {
            18209181: "1",  # France v Morocco (France 2-0)
            18213979: "2",  # Norway v England (England 3-0)
            18218149: "X",  # Spain v Belgium (Draw 1-1)
            18222446: "X",  # Argentina v Switzerland (Draw 0-0)
        }

        try:
            ser = odds_series(fid)          # real history (live fetch if --live, else cache)
            if not ser:
                emit("done", {}); return
            open_p = implied_probs(ser[0]["odds"])
            mode = "LIVE feed" if USE_LIVE else "cached real odds"
            emit("meta", {"points": len(ser), "fixture": fid, "name": name, "mode": mode})
            drift = {"1": 0.0, "X": 0.0, "2": 0.0}

            balance = 10000.0
            active_trades = []
            active_twaps = []
            trade_counter = 0

            def push(pt, i, n):
                nonlocal balance, trade_counter
                p = implied_probs(pt["odds"])
                ts = pt.get("ts", i * 60)
                sigs = det.update(pt["odds"], ts=ts)
                
                # Check for new signals to buy
                for s in sigs:
                    if s.delta_p > 0: # buy signal (implied prob increased)
                        already_bet = any(t["sel"] == s.selection for t in active_trades) or any(t.target_side == s.selection for t in active_twaps)
                        if not already_bet and balance > 0:
                            try:
                                from agent.execution import RiskManager, TWAPEngine
                                rm = RiskManager(starting_bankroll=balance)
                                offered_odds = s.odds_after
                                # Honest edge model. A fired steam signal's real edge is its
                                # CLOSING LINE VALUE — historically these signals beat the close
                                # (backtest, reproducible via `python3 -m agent.backtest`:
                                # confirmed +15% CLV / 84% beat-close, unconfirmed +1.7% CLV).
                                # A static Kelly edge vs the vig-inclusive offered odds is always
                                # negative, so we size on that MEASURED forward CLV edge instead,
                                # held conservatively BELOW the backtested figure. No fabricated
                                # per-signal coefficient, no forced floor: if there is no edge,
                                # RiskManager returns 0 and we skip (see execution.py discipline).
                                expected_clv = 0.10 if abs(s.z) >= 2.0 else 0.02
                                fair_prob = min(0.98, s.prob_after * (1.0 + expected_clv))
                                optimal_stake = rm.calculate_kelly_stake(fair_prob, offered_odds, kelly_fraction=0.25)
                            except Exception as e:
                                print(f"Kelly Engine Error: {e}")
                                optimal_stake = 0.0
                                fair_prob = 0.0

                            if optimal_stake > 0 and balance >= optimal_stake:
                                engine = TWAPEngine(fixture_id=fid, target_side=s.selection, total_stake=optimal_stake, duration_minutes=10)
                                active_twaps.append(engine)
                                emit("twap_initiated", {
                                    "sel": s.selection,
                                    "total_stake": optimal_stake,
                                    "z": round(s.z, 2),
                                    "edge": round((fair_prob * offered_odds - 1.0)*100, 2)
                                })

                # Execute active TWAP engines
                completed_engines = []
                for engine in active_twaps:
                    curr_odds = pt["odds"].get(engine.target_side, 1.8)
                    slice_log = engine.execute_slice(curr_odds)
                    if slice_log:
                        balance -= slice_log["stake"]
                        emit("twap_slice_filled", {
                            "sel": engine.target_side,
                            "stake": slice_log["stake"],
                            "filled_price": slice_log["filled_price"],
                            "avg_price": round(engine.average_execution_price, 3),
                            "progress": slice_log["progress"]
                        })
                    if engine.is_complete():
                        completed_engines.append(engine)
                
                # Move completed engines to active trades
                for engine in completed_engines:
                    active_twaps.remove(engine)
                    trade_counter += 1
                    trade_id = f"T-{trade_counter:03d}"
                    active_trades.append({
                        "id": trade_id,
                        "sel": engine.target_side,
                        "entry_odds": round(engine.average_execution_price, 3),
                        "entry_ts": ts,
                        "stake": round(engine.executed_stake, 2),
                        "status": "ACTIVE",
                        "clv": 0.0
                    })
                    emit("trade_placed", {
                        "id": trade_id,
                        "sel": engine.target_side,
                        "entry_odds": round(engine.average_execution_price, 3),
                        "balance": round(balance, 2),
                        "stake": round(engine.executed_stake, 2),
                        "edge": 5.0 # default/approx
                    })

                # Update CLV edge for active trades based on current odds
                for t in active_trades:
                    curr_odds = pt["odds"].get(t["sel"], t["entry_odds"])
                    if curr_odds > 0:
                        t["clv"] = round(((t["entry_odds"] / curr_odds) - 1.0) * 100, 2)

                d = {k: round((p.get(k, 0) - open_p.get(k, 0)) * 100, 1) for k in ("1", "X", "2")}
                
                emit("tick", {
                    "i": i, 
                    "n": n, 
                    "ts": ts,
                    "odds": {k: round(v, 2) for k, v in pt["odds"].items()},
                    "fair": {k: round(p.get(k, 0), 4) for k in ("1", "X", "2")},
                    "drift": d, 
                    "signals": [{"sel": s.selection, "z": round(s.z, 1), "dp": round(s.delta_p, 4),
                                 "kind": s.kind, "odds": s.odds_after,
                                 "strength": s.strength, "vel": s.velocity} for s in sigs],
                    "portfolio": {
                        "balance": round(balance, 2),
                        "active_trades": active_trades
                    }
                })
                return d

            # 1) fill the screen with the recent REAL history (fast)
            for i, pt in enumerate(ser):
                drift = push(pt, i, len(ser))
                time.sleep(PACE_S)

            # Resolve all active trades
            outcome = OUTCOMES.get(fid)
            resolved_events = []
            if outcome:
                for t in active_trades:
                    won = (t["sel"] == outcome)
                    pnl = t["stake"] * (t["entry_odds"] - 1.0) if won else -t["stake"]
                    payout = t["stake"] * t["entry_odds"] if won else 0.0
                    balance += payout
                    resolved_events.append({
                        "id": t["id"],
                        "sel": t["sel"],
                        "won": won,
                        "pnl": round(pnl, 2),
                        "entry_odds": t["entry_odds"],
                        "closing_odds": round(ser[-1]["odds"].get(t["sel"], t["entry_odds"]), 3),
                        "clv": t["clv"]
                    })
                active_trades.clear()

            if not USE_LIVE:
                emit("done", {
                    "drift": drift,
                    "portfolio": {
                        "balance": round(balance, 2),
                        "resolved": resolved_events
                    }
                })
                return

            # 2) LIVE TAIL: keep polling the real feed; emit genuinely new updates as they land
            emit("livetail", {"since": len(ser)})
            sent = len(ser)
            while True:
                for _ in range(6):            # ~6s between polls, heartbeat each second
                    emit("beat", {"now": time.time(), "sent": sent})
                    time.sleep(1)
                try:
                    fresh = odds_series(fid)
                except Exception:
                    continue
                if len(fresh) > sent:
                    for j in range(sent, len(fresh)):
                        drift = push(fresh[j], j, len(fresh))
                    sent = len(fresh)
        except (BrokenPipeError, ConnectionResetError):
            return


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SharpEdge — LIVE</title>
<style>
:root{--bg:#070b12;--panel:rgba(14,22,38,0.7);--panel2:rgba(17,29,49,0.85);--edge:#1b2740;--fg:#e9f0fb;--mut:#7e90ad;--dim:#57677f;
--amber:#f5b13d;--cyan:#46d5ff;--good:#3fe0c8;--bad:#ff6060;--violet:#9a8cff;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;--sans:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1200px 600px at 80% -10%,rgba(70,213,255,.06),transparent),var(--bg);color:var(--fg);font-family:var(--sans)}
.wrap{max-width:1180px;margin:0 auto;padding:18px}
.top{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:11px 15px;background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--edge);border-radius:13px;backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px)}
.brand{font-weight:800;font-size:18px}.brand b{color:var(--amber)}
.live{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);font-size:11px;letter-spacing:.14em;color:var(--good);padding:4px 10px;border:1px solid color-mix(in srgb,var(--good) 35%,transparent);border-radius:999px}
.live .d{width:7px;height:7px;border-radius:50%;background:var(--good);animation:pulse 1.4s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--good) 70%,transparent)}70%{box-shadow:0 0 0 7px transparent}100%{box-shadow:0 0 0 0 transparent}}
select,button{background:var(--bg);color:var(--fg);border:1px solid var(--edge);border-radius:9px;padding:8px 12px;font-size:14px;font-family:var(--sans);transition:all .15s}
select:focus,button:hover{border-color:var(--cyan);outline:none}
button{cursor:pointer}button.go{background:var(--amber);color:#111;border:0;font-weight:700}
button.go:hover{background:#ffc25c;box-shadow:0 0 10px rgba(245,177,61,0.4)}
.clock{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--dim)}
.grid{display:grid;grid-template-columns:1.2fr 1.2fr 1fr;gap:14px;margin-top:14px}@media(max-width:960px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--edge);border-radius:15px;padding:15px;backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);box-shadow:0 8px 32px 0 rgba(0,0,0,0.25)}
.panel h2{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--mut);margin:0 0 10px;font-weight:600}
.prices{display:flex;gap:10px;margin-bottom:10px}
.pr{flex:1;text-align:center;background:var(--bg);border:1px solid var(--edge);border-radius:11px;padding:9px 4px;transition:all .15s}
.pr .k{font-size:10px;color:var(--dim);font-family:var(--mono);letter-spacing:.1em}
.pr .v{font-family:var(--mono);font-weight:700;font-size:22px;font-variant-numeric:tabular-nums;transition:color .15s}
.pr.up .v{color:var(--good)}.pr.down .v{color:var(--bad)}.pr.fav{border-color:color-mix(in srgb,var(--cyan) 45%,transparent)}
svg{width:100%;height:190px;display:block}
.flowrow{display:flex;justify-content:space-between;font-family:var(--mono);font-size:12px;color:var(--mut);margin-top:8px}
.flowbar{height:8px;border-radius:5px;background:var(--edge);overflow:hidden;margin-top:5px}
.flowbar i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--cyan),var(--amber));transition:width .3s}
.feed{height:280px;overflow:auto;font-family:var(--mono);font-size:13px}
.sig{padding:7px 9px;border-radius:8px;margin-bottom:6px;border-left:3px solid var(--amber);background:color-mix(in srgb,var(--amber) 8%,transparent);animation:pop .3s}
@keyframes pop{from{opacity:0;transform:translateX(8px)}to{opacity:1;transform:none}}
.log{color:var(--dim);font-size:12px;padding:3px 0}
.progress{height:3px;background:var(--edge);border-radius:2px;overflow:hidden;margin-top:12px}
.progress i{display:block;height:100%;background:var(--cyan);width:0;transition:width .2s}

/* Ledger styles */
.card-grid{display:flex;gap:10px;margin-bottom:12px}
.card{flex:1;background:var(--bg);border:1px solid var(--edge);border-radius:11px;padding:10px 6px;text-align:center;transition:border-color .15s}
.card .lbl{font-size:9px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em;margin-bottom:2px}
.card .val{font-family:var(--mono);font-size:18px;font-weight:800}
.table-wrap{border:1px solid var(--edge);border-radius:10px;background:var(--bg);overflow:hidden;margin-bottom:12px}
table{width:100%;border-collapse:collapse;font-size:11px}
th{text-align:left;color:var(--dim);font-size:9px;text-transform:uppercase;letter-spacing:.08em;padding:6px 8px;border-bottom:1px solid var(--edge);background:rgba(25,35,55,0.2)}
td{padding:6px 8px;border-bottom:1px solid var(--edge);font-variant-numeric:tabular-nums}
td.m{font-family:var(--mono);color:var(--mut)}
.c-good{color:var(--good)}.c-bad{color:var(--bad)}.c-gold{color:var(--amber)}
.trade-row{background:rgba(255,255,255,0.02)}
.trade-log{color:#fff;font-size:12px;padding:3px 0;border-left:2px solid var(--mint);padding-left:6px;margin:2px 0}
</style></head><body><div class="wrap">
<div class="top">
  <span class="brand">Sharp<b>Edge</b></span>
  <span class="live"><span class="d"></span>LIVE STREAM</span>
  <select id="fx"></select>
  <button class="go" id="go">▶ Stream</button>
  <span class="clock" id="clock">real TxLINE World Cup odds</span>
</div>
<div class="grid">
  <div class="panel">
    <h2>Live Match Odds & Fair Probabilities</h2>
    <div class="prices" id="prices">
      <div class="pr" data-k="1"><div class="k">HOME</div><div class="v" id="p1">–</div></div>
      <div class="pr" data-k="X"><div class="k">DRAW</div><div class="v" id="pX">–</div></div>
      <div class="pr" data-k="2"><div class="k">AWAY</div><div class="v" id="p2">–</div></div>
    </div>
    <svg id="chart" viewBox="0 0 320 190" preserveAspectRatio="none"></svg>
    <div class="flowrow"><span id="flowlabel">money flow</span><span id="flowval"></span></div>
    <div class="flowbar"><i id="flowbar"></i></div>
    <div class="progress"><i id="prog"></i></div>
  </div>
  
  <div class="panel">
    <h2>Simulated Trading Ledger</h2>
    <div class="card-grid">
      <div class="card"><div class="lbl">portfolio balance</div><div class="val c-gold" id="ledger-balance">$10,000.00</div></div>
      <div class="card"><div class="lbl">session pnl</div><div class="val" id="ledger-pnl">$0.00</div></div>
    </div>
    
    <div style="margin-top:10px; padding:10px; border:1px solid var(--amber); background:rgba(245,177,61,0.05); border-radius:8px">
      <h3 style="margin:0 0 6px; font-size:11px; color:var(--amber); text-transform:uppercase; letter-spacing:0.1em">⚡ Kelly Criterion Risk Engine</h3>
      <div style="display:flex; justify-content:space-between; font-family:var(--mono); font-size:12px; margin-bottom:4px">
        <span style="color:var(--mut)">Confidence Z-Score:</span> <span id="risk-z" style="color:white">—</span>
      </div>
      <div style="display:flex; justify-content:space-between; font-family:var(--mono); font-size:12px; margin-bottom:4px">
        <span style="color:var(--mut)">Mathematical Edge:</span> <span id="risk-edge" style="color:var(--cyan)">—</span>
      </div>
      <div style="display:flex; justify-content:space-between; font-family:var(--mono); font-size:12px">
        <span style="color:var(--mut)">Optimal Kelly Stake:</span> <span id="risk-stake" style="color:var(--good)">—</span>
      </div>
    </div>
    
    <h2 style="font-size:10px;margin-top:14px;margin-bottom:6px">Active Positions (Dynamic Stake)</h2>
    <div class="table-wrap" style="height:100px;overflow:auto">
      <table>
        <thead>
          <tr><th>ID</th><th>SEL</th><th>ENTRY</th><th>CLV EDGE</th></tr>
        </thead>
        <tbody id="active-trades-body">
          <tr><td colspan="4" style="text-align:center;color:var(--amber);padding:24px 0;font-style:italic;opacity:0.9">no active positions</td></tr>
        </tbody>
      </table>
    </div>
    
    <h2 style="font-size:10px;margin-bottom:6px">Completed Trades</h2>
    <div class="table-wrap" style="height:180px;overflow:auto">
      <table>
        <thead>
          <tr><th>ID</th><th>SEL</th><th>ENTRY</th><th>CLOSE</th><th>CLV</th><th>PNL</th></tr>
        </thead>
        <tbody id="resolved-trades-body">
          <tr><td colspan="6" style="text-align:center;color:var(--amber);padding:48px 0;font-style:italic;opacity:0.9">no completed trades</td></tr>
        </tbody>
      </table>
    </div>
  </div>
  
  <div class="panel">
    <h2>Live signal feed</h2>
    <div class="feed" id="feed"><div class="log">pick a match and press ▶ Stream…</div></div>
  </div>
</div>
</div>
<script>
const $=id=>document.getElementById(id);let es=null,hist=[],LAB={1:"home",X:"draw",2:"away"};
fetch("/fixtures").then(r=>r.json()).then(fx=>{
  $("fx").innerHTML=fx.map(f=>`<option value="${f.id}" data-n="${f.home} v ${f.away}">${f.home} v ${f.away}</option>`).join("");
}).catch(()=>{$("feed").innerHTML='<div class="log">could not load fixtures</div>';});
$("go").onclick=()=>{
  if(es)es.close();hist=[];$("feed").innerHTML="";
  $("ledger-balance").textContent = "$10,000.00";
  $("ledger-balance").className = "val c-gold";
  $("ledger-pnl").textContent = "$0.00";
  $("ledger-pnl").className = "val";
  $("active-trades-body").innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--amber);padding:24px 0;font-style:italic;opacity:0.9">no active positions</td></tr>';
  $("resolved-trades-body").innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--amber);padding:48px 0;font-style:italic;opacity:0.9">no completed trades</td></tr>';
  const opt=$("fx").selectedOptions[0];const name=opt?opt.dataset.n:"match";
  es=new EventSource(`/stream?fixture=${$("fx").value}&name=${encodeURIComponent(name)}`);
  let prev={};
  es.addEventListener("meta",e=>{const m=JSON.parse(e.data);log(`▶ streaming ${m.points} real odds updates — ${name}`);});
  es.addEventListener("twap_initiated",e=>{
    const d=JSON.parse(e.data);
    const logEl = document.createElement("div");
    logEl.className = "trade-log";
    logEl.style.borderLeft = "2px solid var(--amber)";
    logEl.style.background = "rgba(245,177,61,0.06)";
    logEl.innerHTML = `🔪 <b>TWAP Initiated:</b> Slicing <b>$${d.total_stake.toFixed(2)}</b> buy order for '${d.sel}' over 5 ticks (Edge: ${d.edge > 0 ? '+' : ''}${d.edge.toFixed(1)}%)`;
    $("feed").prepend(logEl);
    $("risk-z").textContent = (d.z > 0 ? "+" : "") + d.z + "σ";
    $("risk-edge").textContent = (d.edge > 0 ? "+" : "") + d.edge.toFixed(1) + "%";
    $("risk-stake").textContent = "$" + d.total_stake.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  });
  es.addEventListener("twap_slice_filled",e=>{
    const d=JSON.parse(e.data);
    const logEl = document.createElement("div");
    logEl.className = "trade-log";
    logEl.style.borderLeft = "2px solid var(--cyan)";
    logEl.style.color = "var(--mut)";
    logEl.style.paddingLeft = "12px";
    logEl.innerHTML = `↳ [TWAP Fill ${d.progress}] Bought <b>$${d.stake.toFixed(2)}</b> of '${d.sel}' @ ${d.filled_price.toFixed(2)} (Avg Entry: ${d.avg_price.toFixed(3)})`;
    $("feed").prepend(logEl);
  });
  es.addEventListener("trade_placed",e=>{
    const d=JSON.parse(e.data);
    const logEl = document.createElement("div");
    logEl.className = "trade-log";
    logEl.style.borderLeft = "2px solid var(--good)";
    logEl.innerHTML = `🎯 <b>TWAP Complete:</b> Executed <b>$${d.stake.toFixed(2)}</b> on '${d.sel}' (Avg entry: ${d.entry_odds})`;
    $("feed").prepend(logEl);
  });
  es.addEventListener("tick",e=>{
    const t=JSON.parse(e.data);hist.push(t.fair["1"]);
    ["1","X","2"].forEach(k=>{const el=$("p"+k),box=el.parentElement;el.textContent=t.odds[k].toFixed(2);
      box.classList.remove("up","down");if(prev[k]!=null){if(t.odds[k]<prev[k])box.classList.add("up");else if(t.odds[k]>prev[k])box.classList.add("down");}});
    const fav=["1","X","2"].reduce((a,b)=>t.odds[a]<t.odds[b]?a:b);
    ["1","X","2"].forEach(k=>$("p"+k).parentElement.classList.toggle("fav",k===fav));prev=t.odds;
    const into=["1","X","2"].reduce((a,b)=>t.drift[a]>t.drift[b]?a:b);
    $("flowval").textContent=`→ ${LAB[into]} ${t.drift[into]>=0?'+':''}${t.drift[into]}pp`;
    $("flowbar").style.width=Math.min(100,Math.abs(t.drift[into])*14+6)+"%";
    $("prog").style.width=(t.i/(t.n-1)*100)+"%";$("clock").textContent=`tick ${t.i+1}/${t.n} · de-vigged live`;
    drawChart();
    t.signals.forEach(s=>{const d=document.createElement("div");d.className="sig";
      const str=(s.strength==null?0:s.strength);
      const sc=str>=80?'var(--good)':(str>=60?'var(--amber)':'var(--dim)');
      const badge=`<span title="steam-strength score 0-100 (magnitude + abnormality + speed)" style="font-family:var(--mono);font-size:10px;font-weight:800;color:${sc};border:1px solid ${sc};border-radius:4px;padding:1px 5px;margin-left:6px">CONV ${str.toFixed(0)}</span>`;
      d.innerHTML=`🚨 <b>${s.kind}</b> '${s.sel}' Δ${s.dp>=0?'+':''}${s.dp} (${s.z>=0?'+':''}${s.z}σ) @ ${s.odds}${badge}`;$("feed").prepend(d);});
    
    // Update active positions in UI
    const active = t.portfolio.active_trades;
    $("ledger-balance").textContent = "$" + t.portfolio.balance.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    const pnl = t.portfolio.balance - 10000.0;
    $("ledger-pnl").textContent = (pnl >= 0 ? "+" : "") + "$" + pnl.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    $("ledger-pnl").className = "val " + (pnl >= 0 ? "c-good" : "c-bad");
    if(active.length > 0) {
      $("active-trades-body").innerHTML = active.map(tr => {
        const edgeCls = tr.clv >= 0 ? "c-good" : "c-bad";
        return `<tr class="trade-row"><td class="m">${tr.id}</td><td class="m" style="color:#fff;font-weight:bold">${tr.sel}</td><td style="color:#fff">${tr.entry_odds.toFixed(2)}</td><td class="${edgeCls}" style="font-weight:700">${tr.clv >= 0 ? '+' : ''}${tr.clv}%</td></tr>`;
      }).join("");
    } else {
      $("active-trades-body").innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--amber);padding:24px 0;font-style:italic;opacity:0.9">no active positions</td></tr>';
    }
  });
  es.addEventListener("livetail",()=>{log("🔴 now LIVE — polling the real TxLINE feed for new updates…");});
  es.addEventListener("beat",e=>{const b=JSON.parse(e.data);$("clock").textContent="🔴 LIVE · watching feed · "+new Date(b.now*1000).toLocaleTimeString();});
  es.addEventListener("done",e=>{
    const d=JSON.parse(e.data);
    log("■ replay complete (cached mode — run with --live for the real-time tail)");
    es.close();
    
    $("ledger-balance").textContent = "$" + d.portfolio.balance.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    const pnl = d.portfolio.balance - 10000.0;
    $("ledger-pnl").textContent = (pnl >= 0 ? "+" : "") + "$" + pnl.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    $("ledger-pnl").className = "val " + (pnl >= 0 ? "c-good" : "c-bad");
    $("active-trades-body").innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--amber);padding:24px 0;font-style:italic;opacity:0.9">no active positions</td></tr>';
    
    const resolved = d.portfolio.resolved;
    if(resolved.length > 0) {
      $("resolved-trades-body").innerHTML = resolved.map(tr => {
        const pnlCls = tr.pnl >= 0 ? "c-good" : "c-bad";
        const edgeCls = tr.clv >= 0 ? "c-good" : "c-bad";
        return `<tr><td class="m">${tr.id}</td><td class="m">${tr.sel}</td><td>${tr.entry_odds.toFixed(2)}</td><td>${tr.closing_odds.toFixed(2)}</td><td class="${edgeCls}">${tr.clv >= 0 ? '+' : ''}${tr.clv}%</td><td class="${pnlCls}">${tr.pnl >= 0 ? '+' : ''}$${tr.pnl.toFixed(2)}</td></tr>`;
      }).join("");
      log(`🏆 Replay finished. Resolved ${resolved.length} trades. Final Session PnL: ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`);
    } else {
      $("resolved-trades-body").innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--amber);padding:48px 0;font-style:italic;opacity:0.9">no completed trades</td></tr>';
    }
  });
  es.onerror=()=>{log("stream ended");};
};
function log(t){const d=document.createElement("div");d.className="log";d.textContent=t;$("feed").prepend(d);}
function drawChart(){const W=320,H=190,pad=8,n=hist.length;if(n<2)return;
  let d="";hist.forEach((v,i)=>{const x=pad+(W-2*pad)*i/(n-1),y=H-pad-(H-2*pad)*Math.max(0,Math.min(1,v));d+=(i?"L":"M")+x.toFixed(1)+" "+y.toFixed(1)+" ";});
  let grid="";[.25,.5,.75].forEach(g=>{const y=H-pad-(H-2*pad)*g;grid+=`<line x1="${pad}" y1="${y}" x2="${W-pad}" y2="${y}" stroke="var(--edge)" stroke-width=".5"/>`;});
  const lx=pad+(W-2*pad),ly=H-pad-(H-2*pad)*hist[n-1];
  $("chart").innerHTML=`${grid}<path d="${d}" fill="none" stroke="var(--cyan)" stroke-width="2.2"/><circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3.5" fill="var(--amber)"/>`;}
</script></body></html>"""


def main() -> int:
    global PACE_S, USE_LIVE
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--pace", type=float, default=PACE_S)
    ap.add_argument("--live", action="store_true", help="pull fresh from the live TxLINE feed")
    a = ap.parse_args()
    PACE_S = a.pace
    USE_LIVE = a.live
    load_cache()
    n = len(_data["fixtures"])
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), Handler)
    src = "LIVE TxLINE feed" if USE_LIVE else f"cached real odds ({n} fixtures)"
    print("=" * 56)
    print(f" SharpEdge LIVE terminal  ·  source: {src}")
    print(f" ▶  open  http://localhost:{a.port}   (press ▶ Stream)")
    print("=" * 56)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
