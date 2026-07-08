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

## Status
- [x] TxLINE client + auth flow (`txline/client.py`)
- [x] Deterministic sharp-money detector (`agent/detector.py`) — working
- [x] Realistic odds simulator for dev/demo (`agent/simulator.py`)
- [ ] Live devnet feed (on-chain subscribe + activate)
- [ ] LLM explanation layer · outcome tracking/backtest · on-chain settlement · demo
