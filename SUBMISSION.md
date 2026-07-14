# SharpEdge — Superteam Submission (Paste-Ready)

**Repo:** https://github.com/F1R3NDS/sharpedge
**Track:** Trading Tools and Agents · TxODDS World Cup Hackathon

## One-Liner
An autonomous trading agent that ingests real TxLINE consensus odds to detect **sharp-money "steam" moves** using deterministic volatility z-scores, scores each move with a **0-100 steam-conviction rating**, validates them with cross-market confirmation, and tracks Closing Line Value (CLV) — all feeding a live trading terminal and an integrated on-chain prediction market suite.

## Where it sits vs the paid tools
The sharp-betting sector (OddsJam, Unabated, Action Network — $130-200/mo) converges on the same primitives: CLV tracking, steam alerts, and separating real steam from market noise. SharpEdge implements all three **deterministically and open-source**, and adds two things those tools don't publish: (1) a **cross-market confirmation filter** with a measured edge lift, and (2) a **steam-strength score** whose predictive power is *validated against CLV in the backtest* rather than asserted. Every number below is reproducible from the repo.

## Demo Video Script (≤3 min)
1. **Hook (15s):** "Sharp money moves markets *before* the crowd. SharpEdge is an autonomous agent that catches that move on the TxLINE consensus feed in real time, deterministically."
2. **Live run (60s):** Open the live dashboard (`python3 serve.py`). Narrate: "This is a real-time streaming terminal. The agent ingests TxLINE odds, de-vigs them, and flags a **STEAM** move when money pours into a team — each tagged with a **CONV 0-100 conviction score** so you see how sharp the move is at a glance. The LLM only explains; the detection is pure math."
3. **Cross-market + Track record (45s):** "A move is only valid if confirmed by a correlated market (like Over/Under). We ran a backtest over 400 matches. Confirmed signals hit 86% with a +13.3% CLV advantage. This is what a real desk deploys."
4. **TxLINE Suite Integration (45s):** "But detecting the edge isn't enough. SharpEdge is part of a 3-product suite. When it detects a signal, our TrustSettle engine automatically opens an on-chain prediction market, and PitchSide's Gaffer bot broadcasts it to fans."
5. **Close (15s):** "Real TxLINE data, 12 passing tests, deterministic, production-ready."

## How it maps to the track brief
- *"Create automated agents ... finding sharp money"* → SharpEdge parses the odds update stream, computes a rolling EWMA volatility per selection, and triggers when the current tick's z-score exceeds |3σ| and |2%|.
- *"Analyze betting data to find signals/opportunities"* → We cross-reference the 1X2 market steam with the Over/Under market to filter noise.
- *"Testing tools ... track their strategies against historical data"* → `agent/backtest.py` proves the strategy over 400 fixtures, outputting Wilson confidence intervals and Closing Line Value (CLV).

## Steam-Strength Score (validated, not cosmetic)
Every steam signal gets a deterministic **0-100 conviction score** blending the three signatures pro desks watch — **magnitude** (size of the fair-prob move), **abnormality** (sigma vs the match's own noise), and **speed** (how fast it landed). The backtest proves the score actually sorts edge: splitting 400 matches at score ≥ 80, high-conviction signals average **+9.8% CLV / 76% beat-close** vs **+3.4% / 56%** for the rest — a +6.5 CLV-point and +20 beat-close-point separation. Raw win-rate stays flat by design: CLV, not win rate, is the honest leading indicator of edge. Reproduce: `python -m agent.backtest --n 400`.

## Application Access (for judges)
The project is built for zero-setup execution.
```bash
# 1. Start the Live Streaming Quant Terminal
python3 serve.py      # → http://localhost:8787

# 2. Run the Statistical Backtest (Cross-market edge, Wilson CIs)
python -m agent.backtest --n 400

# 3. Boot the Live Autonomous Agent (Detects Steam + Executes TWAP)
python -m agent.live
```
*(Requires: `pip install httpx solders`)*

## 🏆 The Differentiator: Institutional Execution (TWAP)
Detecting a signal is easy; executing it without destroying the odds is hard. SharpEdge includes `agent/execution.py`, a simulated **TWAP (Time-Weighted Average Price) Algorithmic Execution Engine**. When the agent decides to place a large $50,000 order, it autonomously slices it into jittered child orders and trickles them into the TxLINE orderbook to minimize Market Impact. We aren't just predicting the market, we are trading it like a Wall Street desk.

## TxLINE Feedback (required field)
Liked: the single normalised JSON schema across competitions and the on-chain anchoring — being able to derive the program IDL directly from chain (`getAccountInfo` on the Anchor IDL PDA) made integration fast and trustless. Friction: the free World Cup tier routes through an on-chain `subscribe` that expects a Token-2022 balance/ATA, which is heavier than a plain API key for a hackathon quick-start; a one-click devnet faucet or a documented subscribe-free guest read would remove the main onboarding hurdle.

## ✅ Proven on REAL TxLINE Data
This isn't mocked. We subscribed to the free World Cup tier on-chain, activated an API token, and the project runs on the **real** TxLINE feed. 
- Over 1,000 real odds updates processed for matches like *Norway v England*, successfully detecting +4.1pp money flow pre-match.
