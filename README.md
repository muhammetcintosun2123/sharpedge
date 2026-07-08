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
python -m agent.run  --sim                  # autonomous daemon on one fixture
python -m pytest -q                         # determinism + scoring tests
```

## Status
- [x] TxLINE client + auth flow (`txline/client.py`), devnet access solved (`txline/access.md`)
- [x] Deterministic sharp-money detector (`agent/detector.py`) — z-score, de-vig, two hard gates
- [x] LLM explanation layer (`agent/reason.py`) — explains only, never decides; degrades without a key
- [x] Dual track record: outcome P&L **+ CLV** (`agent/tracker.py`)
- [x] Autonomous daemon loop (`agent/run.py`) + portfolio demo (`agent/demo.py`)
- [x] Deterministic-behaviour tests (`tests/test_core.py`)
- [~] Live devnet feed: HTTP/auth wired; on-chain `subscribe` gated behind TxODDS free-tier
      token mint (brief allows live **or** simulated — schema-faithful simulator used for the demo)
