"""
agent/livehtml.py — build a SELF-CONTAINED live terminal (no server, no python at runtime).

Embeds the precomputed real tick stream (out/live_playback.json — real de-vigged odds +
detector output) into one HTML file that animates the feed client-side: press ▶ and the
odds tick, the chart draws, and signals fire — exactly like the server version, but it
opens by double-clicking the file or via an Artifact link. Nothing to install or run.

  python -m agent.livehtml        # writes out/live.html + out/live_artifact.html
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PB = _ROOT / "out" / "live_playback.json"
_OUT = _ROOT / "out" / "live.html"
_ART = _ROOT / "out" / "live_artifact.html"


def build() -> Path:
    data = json.loads(_PB.read_text())
    html = _TEMPLATE.replace("/*__DATA__*/", json.dumps(data, separators=(",", ":")))
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(html)
    style = re.search(r"<style>.*?</style>", html, re.DOTALL).group(0)
    body = re.search(r"<body>(.*)</body>", html, re.DOTALL).group(1)
    _ART.write_text(style + "\n" + body)
    return _OUT


_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SharpEdge — LIVE</title>
<style>
:root{--bg:#070b12;--panel:#0e1626;--panel2:#111d31;--edge:#1b2740;--fg:#e9f0fb;--mut:#7e90ad;--dim:#57677f;
--amber:#f5b13d;--cyan:#46d5ff;--good:#40d98a;--bad:#ff6060;--violet:#9a8cff;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;--sans:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
@media(prefers-color-scheme:light){:root{--bg:#eef2f8;--panel:#fff;--panel2:#f5f8fc;--edge:#dbe3ee;--fg:#0d1a2b;--mut:#55638a;--dim:#8496ad}}
:root[data-theme=light]{--bg:#eef2f8;--panel:#fff;--panel2:#f5f8fc;--edge:#dbe3ee;--fg:#0d1a2b;--mut:#55638a;--dim:#8496ad}
:root[data-theme=dark]{--bg:#070b12;--panel:#0e1626;--panel2:#111d31;--edge:#1b2740;--fg:#e9f0fb;--mut:#7e90ad;--dim:#57677f}
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
.pr{flex:1;text-align:center;background:var(--bg);border:1px solid var(--edge);border-radius:11px;padding:9px 4px}
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
.progress{height:3px;background:var(--edge);border-radius:2px;overflow:hidden;margin-top:12px}
.progress i{display:block;height:100%;background:var(--cyan);width:0;transition:width .2s}
.src{color:var(--dim);font-size:12px;font-family:var(--mono);margin-top:14px;text-align:center}
</style></head><body><div class="wrap">
<div class="top">
  <span class="brand">Sharp<b>Edge</b></span>
  <span class="live"><span class="d"></span>LIVE</span>
  <select id="fx"></select>
  <button class="go" id="go">▶ Play</button>
  <span class="clock" id="clock">real TxLINE World Cup odds</span>
</div>
<div class="grid">
  <div class="panel">
    <div class="prices">
      <div class="pr" data-k="1"><div class="k">HOME</div><div class="v" id="p1">–</div></div>
      <div class="pr" data-k="X"><div class="k">DRAW</div><div class="v" id="pX">–</div></div>
      <div class="pr" data-k="2"><div class="k">AWAY</div><div class="v" id="p2">–</div></div>
    </div>
    <svg id="chart" viewBox="0 0 320 190" preserveAspectRatio="none"></svg>
    <div class="flowrow"><span>money flow</span><span id="flowval"></span></div>
    <div class="flowbar"><i id="flowbar"></i></div>
    <div class="progress"><i id="prog"></i></div>
  </div>
  <div class="panel">
    <h2>Live signal feed</h2>
    <div class="feed" id="feed"><div class="log">pick a match and press ▶ Play…</div></div>
  </div>
</div>
<div class="src" id="src"></div>
</div>
<script>
const DATA=/*__DATA__*/;const $=id=>document.getElementById(id);const LAB={1:"home",X:"draw",2:"away"};
$("src").textContent=DATA.source;
DATA.fixtures.forEach((f,i)=>{const o=document.createElement("option");o.value=i;o.textContent=`${f.home} v ${f.away}`;$("fx").appendChild(o);});
let timer=null,hist=[],prev={};
function stop(){if(timer){clearInterval(timer);timer=null;$("go").textContent="▶ Play";}}
$("go").onclick=()=>{
  if(timer){stop();return;}
  const f=DATA.fixtures[+$("fx").value];hist=[];prev={};$("feed").innerHTML="";
  log(`▶ streaming ${f.ticks.length} real odds updates — ${f.home} v ${f.away}`);
  $("go").textContent="⏸ Pause";let i=0;
  timer=setInterval(()=>{
    if(i>=f.ticks.length){log("■ real market history replayed");stop();return;}
    const t=f.ticks[i];hist.push(t.f["1"]);
    ["1","X","2"].forEach(k=>{const el=$("p"+k),box=el.parentElement;el.textContent=t.o[k].toFixed(2);
      box.classList.remove("up","down");if(prev[k]!=null){if(t.o[k]<prev[k])box.classList.add("up");else if(t.o[k]>prev[k])box.classList.add("down");}});
    const fav=["1","X","2"].reduce((a,b)=>t.o[a]<t.o[b]?a:b);["1","X","2"].forEach(k=>$("p"+k).parentElement.classList.toggle("fav",k===fav));prev=t.o;
    const into=["1","X","2"].reduce((a,b)=>t.d[a]>t.d[b]?a:b);
    $("flowval").textContent=`→ ${LAB[into]} ${t.d[into]>=0?'+':''}${t.d[into]}pp`;
    $("flowbar").style.width=Math.min(100,Math.abs(t.d[into])*14+6)+"%";
    $("prog").style.width=(i/(f.ticks.length-1)*100)+"%";$("clock").textContent=`tick ${i+1}/${f.ticks.length} · de-vigged`;
    draw();
    (t.s||[]).forEach(s=>{const d=document.createElement("div");d.className="sig";d.innerHTML=`🚨 <b>${s.kind}</b> '${s.sel}' Δ${s.dp>=0?'+':''}${s.dp} (${s.z>=0?'+':''}${s.z}σ) @ ${s.odds}`;$("feed").prepend(d);});
    i++;
  },140);
};
function log(t){const d=document.createElement("div");d.className="log";d.textContent=t;$("feed").prepend(d);}
function draw(){const W=320,H=190,pad=8,n=hist.length;if(n<2)return;let d="";
  hist.forEach((v,i)=>{const x=pad+(W-2*pad)*i/(n-1),y=H-pad-(H-2*pad)*Math.max(0,Math.min(1,v));d+=(i?"L":"M")+x.toFixed(1)+" "+y.toFixed(1)+" ";});
  let g="";[.25,.5,.75].forEach(z=>{const y=H-pad-(H-2*pad)*z;g+=`<line x1="${pad}" y1="${y}" x2="${W-pad}" y2="${y}" stroke="var(--edge)" stroke-width=".5"/>`;});
  const lx=pad+(W-2*pad),ly=H-pad-(H-2*pad)*hist[n-1];
  $("chart").innerHTML=`${g}<path d="${d}" fill="none" stroke="var(--cyan)" stroke-width="2.2"/><circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3.5" fill="var(--amber)"/>`;}
</script></body></html>"""


def main() -> int:
    p = build()
    print(f"self-contained live terminal: {p}")
    print(f"artifact body: {_ART}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
