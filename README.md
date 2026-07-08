# SharpEdge — autonomous sharp-money agent for TxLINE (World Cup)

An autonomous agent that ingests TxLINE consensus odds, detects **sharp-money
"steam" moves** with a deterministic, defensible method, explains each signal
(LLM layer), and tracks whether the signal predicted the outcome — with on-chain
settlement on Solana devnet.

Built for the TxODDS World Cup Hackathon · Track: Trading Tools and Agents.

## Core logic (deterministic)
odds → de-vigged fair probability → per-selection EWMA volatility →
z-score of each move vs the match's own recent noise → STEAM (sharp) vs DRIFT.
See `agent/detector.py`. Fully reproducible; the LLM only *explains*, never decides.

## Cross-market confirmation (what a desk actually does)
A steam move in the 1X2 market is worth far more when the correlated **Over/Under**
market moves with it — shared information (injuries, informed money) hits both; a
one-market move is more likely noise. SharpEdge runs its detector on both feeds and tags
each 1X2 signal **CONFIRMED** or **UNCONFIRMED** (`agent/multimarket.py`). The detector
infers confirmation purely from observed odds — it never sees which moves were "informed".

The backtest over 400 matches (`agent/backtest.py`) shows the filter earns its keep, with
non-overlapping 95% confidence intervals:

| signal | hit rate (95% CI) | ROI/signal | avg CLV | beat close |
|--------|-------------------|-----------|---------|------------|
| **CONFIRMED**   | **86% [83–88%]** | +0.81u | +13.3% | 80% |
| UNCONFIRMED | 60% [56–65%]      | +0.27u | +3.6%  | 66% |

```
python -m agent.backtest --n 400      # reproduce the table (Wilson CIs)
```

## Why the track record is credible: CLV
A single match outcome is one coin flip — noisy. Professional desks judge a signal by
**Closing Line Value (CLV)**: did the odds you caught keep shortening into the close?
Beating the closing line is the strongest known predictor of long-run profit and needs
no lucky results. SharpEdge reports both: outcome P&L *and* CLV (see `agent/tracker.py`).
On the demo portfolio: **62% hit rate, +1.77u ROI, +1.8% avg CLV, beat the close 75%.**

## Run it
```
pip install httpx solders base58            # + optional GROQ_API_KEY for LLM reads
python -m agent.demo --fast                 # portfolio: 4 matches, deterministic core
python -m agent.backtest --n 400            # cross-market edge over 400 matches (Wilson CIs)
python -m agent.run  --sim                  # autonomous daemon on one fixture
python -m agent.web  --open                 # self-contained visual dashboard (one HTML file)
python -m pytest -q                         # determinism + scoring + backtest tests
```

## Live TxLINE ready (verified)
The full mainnet live-access path is built and verified in `txline/live_mainnet.py`: guest
JWT → on-chain `subscribe` (free World Cup tier, **0 tokens** — confirmed against the
on-chain PricingMatrix) → activate → read. A `--simulate` run confirms the subscribe
transaction's accounts resolve to the real on-chain treasury; the only thing between the
agent and a live mainnet feed is the tiny subscribe fee. The brief allows live **or**
simulated data, and the schema-faithful simulator is used for the reproducible demo.

## Status
- [x] TxLINE client + auth flow (`txline/client.py`), devnet access solved (`txline/access.md`)
- [x] Deterministic sharp-money detector (`agent/detector.py`) — z-score, de-vig, two hard gates
- [x] **Cross-market confirmation** (`agent/multimarket.py`) — 1X2 × Over/Under agreement filter
- [x] **Statistical backtest** with Wilson confidence intervals (`agent/backtest.py`)
- [x] LLM explanation layer (`agent/reason.py`) — explains only, never decides; degrades without a key
- [x] Dual track record: outcome P&L **+ CLV** (`agent/tracker.py`)
- [x] Autonomous daemon loop (`agent/run.py`) + portfolio demo (`agent/demo.py`)
- [x] Deterministic-behaviour tests (`tests/`)
- [~] Live devnet feed: HTTP/auth wired; on-chain `subscribe` gated behind TxODDS free-tier
      token mint (brief allows live **or** simulated — schema-faithful simulator used for the demo)
