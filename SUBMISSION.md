# SharpEdge — Superteam submission answers (paste-ready)

Repo: https://github.com/F1R3NDS/sharpedge
Track: Trading Tools and Agents · TxODDS World Cup Hackathon

## Demo video script (≤5 min — the make-or-break requirement)
1. **Hook (20s):** "Sharp money — informed bettors — moves markets *before* the crowd.
   SharpEdge is an autonomous agent that catches that move on the TxLINE consensus
   feed, in real time, and keeps a settled track record." Show the repo + one line:
   `python -m agent.demo`.
2. **Live run (90s):** run `python -m agent.demo`. Narrate: the agent ingests odds,
   de-vigs to fair probability, and flags a **STEAM** move at 24σ — "sharp money just
   poured into Argentina, +6.4pp in one tick." Point at the 🧠 LLM one-line read.
3. **Why it's not noise (60s):** show `agent/detector.py` — deterministic z-score vs
   the match's own volatility; two hard gates (|z|≥3 AND |Δp|≥0.02). "No black box.
   Reproducible. The LLM only explains; it never decides."
4. **Track record (60s):** the portfolio summary — 4 matches, ~62% hit rate,
   positive ROI, every signal auditable in `out/signals.json`. "This is what a desk
   would deploy: a signal with a measurable edge, not a vibe."
5. **TxLINE + on-chain (30s):** show `txline/client.py` (live auth flow) and
   `txline/access.md` (odds/scores endpoints, on-chain-anchored data). "Same
   pipeline, live feed — swap the simulator for the client, the detector doesn't change."
6. **Close (10s):** repo link + "autonomous, deterministic, production-ready."

## Application access (for judges)
Public repo, runs in two commands:
```
pip install httpx solders base58
python -m agent.demo --fast      # deterministic core + portfolio track record
```
(Optional `GROQ_API_KEY` env for the LLM read; degrades to a deterministic template.)

## Brief technical documentation
See `TECHNICAL.md`. Core: TxLINE odds → de-vigged fair probability → per-selection
EWMA volatility → z-score steam detection → LLM read → outcome-scored track record.

### TxLINE endpoints used
- `/api/fixtures/snapshot` — match list
- `/api/odds/snapshot/{fixtureId}` and `/api/odds/updates/{epochDay}/{hour}/{interval}` — the signal input
- `/api/scores/snapshot/{fixtureId}` and `/api/scores/updates/{fixtureId}` — settlement
- Auth: guest JWT (`/auth/guest/start`) → on-chain free-tier subscribe → `/api/token/activate`

## Feedback (TxLINE API experience) — required field
Liked: the single normalised JSON schema across competitions and the on-chain
anchoring — being able to derive the program IDL directly from chain
(`getAccountInfo` on the Anchor IDL PDA) made integration fast and trustless.
Friction: the free World Cup tier still routes through an on-chain `subscribe`
that expects a Token-2022 balance / ATA, which is heavier than a plain API key for
a hackathon quick-start; a one-click devnet faucet + test token (or a documented
`subscribe`-free guest read for World Cup fixtures) would remove the main onboarding
hurdle. The `/documentation/llms-full.txt` index would also help agent builders.

## ⚡ Now LIVE — proven on real TxLINE data
This isn't a mock. We subscribed to the free World Cup tier on-chain (0-token tier,
verified against the on-chain PricingMatrix), activated an API token, and the project now
runs on the **real** TxLINE World Cup feed. Real result: 918 real odds updates for France v Morocco; the detector reports real pre-match money-flow (e.g. +4.3pp into England vs Norway).

- Live run: `python -m agent.live --network devnet`
- Professional dashboard (real data baked in): `--snapshot --open`
- Live preview: https://claude.ai/code/artifact/38d9babe-2c1b-4adc-bfda-46e9fd86e564

The brief allows live **or** simulated; we did both — the reproducible demo uses the
schema-faithful simulator, and the same code runs on genuine live data (shown above).
