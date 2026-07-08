"""
serve.py — SharpEdge LIVE terminal: a real streaming web app for the demo.

A stdlib HTTP server (no deps) that streams real TxLINE World Cup odds over Server-Sent
Events, runs the deterministic detector on every tick server-side, and pushes each tick +
any signal to a live-updating browser terminal. This is the screen you record: real market
data moving in real time, the agent reacting live.

  python serve.py                 # http://localhost:8787  (replays real odds as a live feed)
  python serve.py --live-poll     # instead poll the real feed every 20s (true real-time)

Data is REAL: fetched from the subscribed TxLINE devnet feed (competition 72, World Cup).
Replay streams the genuine 800-900-point odds history per fixture at a watchable pace.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent.detector import SharpDetector, implied_probs
from txline import live_mainnet as L
from txline import live_feed as F

PACE_S = 0.35          # seconds between replayed ticks
_cache = {}            # fixture_id -> real odds series (fetched once)


def series(fixture_id: int):
    if fixture_id not in _cache:
        _cache[fixture_id] = F.odds_series(fixture_id)
    return _cache[fixture_id]


def fixtures():
    return F.fixtures(72)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self._send(200, "text/html; charset=utf-8", PAGE.encode())
        elif self.path == "/fixtures":
            fx = [{"id": f["FixtureId"], "home": f["Participant1"], "away": f["Participant2"]}
                  for f in fixtures()]
            self._send(200, "application/json", json.dumps(fx).encode())
        elif self.path.startswith("/stream"):
            self.stream()
        else:
            self._send(404, "text/plain", b"not found")

    def stream(self):
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        fid = int(q.get("fixture", ["0"])[0]) or fixtures()[0]["FixtureId"]
        name = q.get("name", ["match"])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def emit(event, payload):
            self.wfile.write(f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode())
            self.wfile.flush()

        ser = series(fid)
        det = SharpDetector(fixture_id=fid, match=name)
        open_p = implied_probs(ser[0]["odds"]) if ser else {}
        try:
            emit("meta", {"points": len(ser), "fixture": fid, "name": name,
                          "open": {k: round(open_p.get(k, 0), 4) for k in ("1", "X", "2")}})
            for i, pt in enumerate(ser):
                p = implied_probs(pt["odds"])
                sigs = [{"sel": s.selection, "z": round(s.z, 1), "dp": round(s.delta_p, 4),
                         "kind": s.kind, "odds": s.odds_after}
                        for s in det.update(pt["odds"], ts=pt["ts"])]
                drift = {k: round((p.get(k, 0) - open_p.get(k, 0)) * 100, 1) for k in ("1", "X", "2")}
                emit("tick", {"i": i, "n": len(ser),
                              "odds": {k: round(v, 2) for k, v in pt["odds"].items()},
                              "fair": {k: round(p.get(k, 0), 4) for k in ("1", "X", "2")},
                              "drift": drift, "signals": sigs})
                time.sleep(PACE_S)
            emit("done", {"drift": drift})
        except (BrokenPipeError, ConnectionResetError):
            return


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SharpEdge — LIVE</title>
<style>
:root{--bg:#070b12;--panel:#0e1626;--panel2:#111d31;--edge:#1b2740;--fg:#e9f0fb;--mut:#7e90ad;--dim:#57677f;
--amber:#f5b13d;--cyan:#46d5ff;--good:#40d98a;--bad:#ff6060;--violet:#9a8cff;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;--sans:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1200px 600px at 80% -10%,rgba(70,213,255,.06),transparent),var(--bg);color:var(--fg);font-family:var(--sans)}
.wrap{max-width:1080px;margin:0 auto;padding:18px}
.top{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:11px 15px;background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--edge);border-radius:13px}
.brand{font-weight:800;font-size:18px}.brand b{color:var(--amber)}
.live{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);font-size:11px;letter-spacing:.14em;color:var(--good);padding:4px 10px;border:1px solid color-mix(in srgb,var(--good) 35%,transparent);border-radius:999px}
.live .d{width:7px;height:7px;border-radius:50%;background:var(--good);animation:pulse 1.4s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--good) 70%,transparent)}70%{box-shadow:0 0 0 7px transparent}100%{box-shadow:0 0 0 0 transparent}}
select,button{background:var(--panel);color:var(--fg);border:1px solid var(--edge);border-radius:9px;padding:8px 12px;font-size:14px;font-family:var(--sans)}
button{cursor:pointer}button.go{background:var(--amber);color:#111;border:0;font-weight:700}
.clock{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--dim)}
.grid{display:grid;grid-template-columns:1.5fr 1fr;gap:14px;margin-top:14px}@media(max-width:820px){.grid{grid-template-columns:1fr}}
.panel{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--edge);border-radius:15px;padding:15px}
.panel h2{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:var(--mut);margin:0 0 10px;font-weight:600}
.prices{display:flex;gap:10px;margin-bottom:10px}
.pr{flex:1;text-align:center;background:var(--bg);border:1px solid var(--edge);border-radius:11px;padding:9px 4px;transition:border-color .2s}
.pr .k{font-size:10px;color:var(--dim);font-family:var(--mono);letter-spacing:.1em}
.pr .v{font-family:var(--mono);font-weight:700;font-size:22px;font-variant-numeric:tabular-nums;transition:color .15s}
.pr.up .v{color:var(--good)}.pr.down .v{color:var(--bad)}.pr.fav{border-color:color-mix(in srgb,var(--cyan) 45%,transparent)}
svg{width:100%;height:190px;display:block}
.flowrow{display:flex;justify-content:space-between;font-family:var(--mono);font-size:12px;color:var(--mut);margin-top:8px}
.flowbar{height:8px;border-radius:5px;background:var(--edge);overflow:hidden;margin-top:5px}
.flowbar i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--cyan),var(--amber));transition:width .3s}
.feed{height:250px;overflow:auto;font-family:var(--mono);font-size:13px}
.sig{padding:7px 9px;border-radius:8px;margin-bottom:6px;border-left:3px solid var(--amber);background:color-mix(in srgb,var(--amber) 8%,transparent);animation:pop .3s}
@keyframes pop{from{opacity:0;transform:translateX(8px)}to{opacity:1;transform:none}}
.log{color:var(--dim);font-size:12px;padding:3px 0}
.big{font-family:var(--mono);font-size:30px;font-weight:800;font-variant-numeric:tabular-nums}
.progress{height:3px;background:var(--edge);border-radius:2px;overflow:hidden;margin-top:12px}
.progress i{display:block;height:100%;background:var(--cyan);width:0;transition:width .2s}
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
    <h2>Live signal feed</h2>
    <div class="feed" id="feed"><div class="log">connect and press ▶ Stream…</div></div>
  </div>
</div>
</div>
<script>
const $=id=>document.getElementById(id);let es=null,hist=[],LAB={1:"home",X:"draw",2:"away"};
fetch("/fixtures").then(r=>r.json()).then(fx=>{
  $("fx").innerHTML=fx.map(f=>`<option value="${f.id}" data-n="${f.home} v ${f.away}">${f.home} v ${f.away}</option>`).join("");
});
$("go").onclick=()=>{
  if(es)es.close();hist=[];$("feed").innerHTML="";
  const opt=$("fx").selectedOptions[0];const name=opt?opt.dataset.n:"match";
  const url=`/stream?fixture=${$("fx").value}&name=${encodeURIComponent(name)}`;
  es=new EventSource(url);
  let prev={};
  es.addEventListener("meta",e=>{const m=JSON.parse(e.data);log(`▶ streaming ${m.points} real odds updates — ${name}`);});
  es.addEventListener("tick",e=>{
    const t=JSON.parse(e.data);hist.push(t.fair["1"]);
    ["1","X","2"].forEach(k=>{const el=$("p"+k);const box=el.parentElement;
      el.textContent=t.odds[k].toFixed(2);
      box.classList.remove("up","down");
      if(prev[k]!=null){if(t.odds[k]<prev[k])box.classList.add("up");else if(t.odds[k]>prev[k])box.classList.add("down");}
    });
    const fav=["1","X","2"].reduce((a,b)=>t.odds[a]<t.odds[b]?a:b);
    ["1","X","2"].forEach(k=>$("p"+k).parentElement.classList.toggle("fav",k===fav));
    prev=t.odds;
    const into=["1","X","2"].reduce((a,b)=>t.drift[a]>t.drift[b]?a:b);
    $("flowval").textContent=`→ ${LAB[into]} ${t.drift[into]>=0?'+':''}${t.drift[into]}pp`;
    $("flowbar").style.width=Math.min(100,Math.abs(t.drift[into])*14+6)+"%";
    $("prog").style.width=(t.i/(t.n-1)*100)+"%";
    $("clock").textContent=`tick ${t.i+1}/${t.n} · de-vigged live`;
    drawChart();
    t.signals.forEach(s=>{const d=document.createElement("div");d.className="sig";
      d.innerHTML=`🚨 <b>${s.kind}</b> '${s.sel}' Δ${s.dp>=0?'+':''}${s.dp} (${s.z>=0?'+':''}${s.z}σ) @ ${s.odds}`;
      $("feed").prepend(d);});
  });
  es.addEventListener("done",e=>{log("■ stream complete — real market history replayed");es.close();});
  es.onerror=()=>{log("stream ended");};
};
function log(t){const d=document.createElement("div");d.className="log";d.textContent=t;$("feed").prepend(d);}
function drawChart(){const W=320,H=190,pad=8,n=hist.length;if(n<2)return;
  let d="";hist.forEach((v,i)=>{const x=pad+(W-2*pad)*i/(n-1);const y=H-pad-(H-2*pad)*Math.max(0,Math.min(1,v));d+=(i?"L":"M")+x.toFixed(1)+" "+y.toFixed(1)+" ";});
  let grid="";[.25,.5,.75].forEach(g=>{const y=H-pad-(H-2*pad)*g;grid+=`<line x1="${pad}" y1="${y}" x2="${W-pad}" y2="${y}" stroke="var(--edge)" stroke-width=".5"/>`;});
  const lx=pad+(W-2*pad);const ly=H-pad-(H-2*pad)*hist[n-1];
  $("chart").innerHTML=`${grid}<path d="${d}" fill="none" stroke="var(--cyan)" stroke-width="2.2"/><circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3.5" fill="var(--amber)"/>`;
}
</script></body></html>"""


def main() -> int:
    global PACE_S
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--network", choices=["mainnet", "devnet"], default="devnet")
    ap.add_argument("--pace", type=float, default=PACE_S)
    a = ap.parse_args()
    PACE_S = a.pace
    L.set_network(a.network)
    print(f"SharpEdge LIVE — warming real feed…")
    fx = fixtures()
    print(f"  {len(fx)} live World Cup fixtures ready")
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), Handler)
    print(f"\n▶ open  http://localhost:{a.port}  and press Stream (real TxLINE odds, live)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
