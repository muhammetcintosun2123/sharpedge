# SharpEdge — Technical Documentation

**Track:** Trading Tools and Agents · TxODDS World Cup Hackathon
**One line:** an autonomous agent that ingests TxLINE consensus odds, detects
sharp-money "steam" moves with deterministic, defensible math, explains each in
plain language, and keeps an auditable, settled-on-chain track record.

## Core idea
Sharp (informed) money reveals itself as a **steam move** — a fast, large, one-
directional shift in the *consensus* implied probability that stands out against a
match's own recent noise. SharpEdge quantifies this without any black box:

1. **De-vig** — decimal odds → `p = 1/odds`, normalized across the 1X2 market so
   probabilities sum to 1 (removes the bookmaker margin → *fair* probability).
2. **Per-selection volatility** — EWMA variance of Δp (each selection's own noise).
3. **Standardized move** — `z = Δp / σ`, using the *prior* volatility (the current
   move is folded into σ only afterwards, so a real jump isn't self-masked).
4. **Trigger** — flag when `|z| ≥ 3` **and** `|Δp| ≥ 0.02` (statistically abnormal
   *and* materially large). Classify **STEAM** (fast) vs **DRIFT** (slow grind).
5. **Score** — a money-IN signal (Δp>0) predicts that selection; on settlement we
   compute hit-rate and ROI (stake 1u at the flagged odds).

The logic is fully deterministic and unit-reproducible. The **LLM only explains**
a signal after the fact (direction is decided in code and passed in fixed) — it
never influences the decision, so "clean, deterministic, defensible logic" holds.

## Architecture
```
txline/client.py     TxLINE REST client + full auth flow (guest JWT → activate → reads)
txline/access.md     resolved devnet access facts (IDL, PDAs, mints, discriminator)
txline/idl/          on-chain-fetched program IDL (txoracle v1.4.2)
agent/detector.py    deterministic sharp-money detector  ← the core
agent/reason.py      LLM one-line read (direction-explicit; template fallback, no hard dep)
agent/tracker.py     signal → outcome scoring (hit-rate, ROI)
agent/simulator.py   outcome-aware odds stream (dev/demo; models sharp's real edge)
agent/run.py         single-match autonomous loop
agent/demo.py        portfolio run across matches → aggregate track record
```

## TxLINE integration
- Endpoints used: `/api/fixtures/snapshot`, `/api/odds/snapshot/{fixtureId}`,
  `/api/odds/updates/{epochDay}/{hourOfDay}/{interval}`, `/api/scores/snapshot|updates/{fixtureId}`.
- Auth (implemented in `txline/client.py`): guest JWT → on-chain free-tier
  `subscribe(level, weeks)` → sign `txSig:leagues:jwt` → `/api/token/activate` →
  requests carry `Authorization: Bearer` + `X-Api-Token`.
- Odds → the detector's `{"1","X","2"}` decimal map; scores → settlement.
- Devnet program `6pW64gN1s2uqjHkn1unFeEjAwJkPGHoppGvS715wyP2J`; all subscribe
  accounts/PDAs/mints resolved (see `txline/access.md`).

## Autonomy & production readiness
- Once started the loop runs unattended (poll → detect → explain → record → settle).
- No hard external dependency: the LLM read degrades to a deterministic template if
  no key is set, so the core tool never stops.
- Auditable output: every signal + the settled track record persist to `out/signals.json`.

## Reproduce
```bash
pip install httpx solders base58            # + optional GROQ_API_KEY for LLM reads
python -m agent.demo --fast                 # deterministic core, portfolio track record
python -m agent.demo                        # with LLM one-line reads
```

## Extension points (built, ready to wire live)
- Live feed: activate TxLINE tokens (user wallet or hackathon test token) → `txline/client.py`
  swaps in for the simulator with zero change to the detector.
- On-chain settlement: anchor each signal + its outcome to Solana devnet (TxLINE data
  is itself on-chain anchored → verifiable end-to-end).
