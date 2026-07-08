# TxLINE devnet access — resolved facts

Program (devnet): `6pW64gN1s2uqjHkn1unFeEjAwJkPGHoppGvS715wyP2J` (`txoracle` v1.4.2)
API origin (devnet): `https://txline-dev.txodds.com`
Guest JWT: `POST /auth/guest/start` → `{token}` (WORKS, no wallet)

## subscribe instruction (from on-chain IDL)
- `subscribe(service_level_id: u16, weeks: u8)` — discriminator `[254,28,191,138,156,179,183,53]`
- Free World Cup tier: service_level_id = 1 (60s delay) or 12 (realtime), weeks = 4
- Accounts (order):
  1. user (signer, writable)
  2. pricing_matrix = `B4hHn1FpD1YPPrcM4yUrQhBPF18zFWgijHLTsumGzeKi`  (PDA ["pricing_matrix"])
  3. token_mint = one of the two TxL mints (Token-2022, 6 decimals):
     `4Zao8ocPhmMgq7PdsYWyxvqySMGx7xb9cMftPMkEokRG` or `AfDqUk86FphPTZdSCRBg5bGm6v4Enamnjc3twqQzsVb1`
  4. user_token_account = ATA(user, mint, Token-2022)  (writable)
  5. token_treasury_vault = ATA(token_treasury_pda, mint, Token-2022)  (writable)
  6. token_treasury_pda = `Eqqd7rZQGzn2HA9L11NwBMhknxArM3L4KETyUuujK3LB`  (PDA ["token_treasury_v2"])
  7. token_program = `TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb` (Token-2022)
  8. system_program = `11111111111111111111111111111111`
  9. associated_token_program = `ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL`

## activation
1. sign message `"{txSig}:{leagues_csv}:{jwt}"` with the subscribing wallet (Ed25519, detached), base64
2. `POST /api/token/activate {txSig, walletSignature, leagues}` with `Authorization: Bearer {jwt}` → `{token}` (X-Api-Token)
3. reads: headers `Authorization: Bearer {jwt}` + `X-Api-Token: {apiToken}`

## Barrier / intended path
The subscribe ix requires a Token-2022 TxL balance (constants: MIN_USER_BALANCE=1_000_000 = 1 token @6dp;
SUBSCRIPTION_PRICE_TOKEN=1). The free World Cup tier is meant to be done through the TxODDS site's own
"Subscribe to Free Tier" button with the participant's wallet (it handles ATA + token). Two ways to get live:
  (A) user connects Phantom on txline docs/app → Subscribe Free Tier → we read the activated tokens; or
  (B) ask TxODDS Discord/Telegram for a devnet hackathon test token (they offer real-time support).
Until then the agent runs on the schema-faithful simulator (brief allows "live OR simulated").

## MAINNET (live World Cup free tier) — VERIFIED 2026-07-08
Program: `9ExbZjAapQww1vfcisDmrngPinHTEfpjYRWMunJgcKaA` (txoracle v1.5.5)
API: `https://txline.txodds.com` — guest JWT `POST /auth/guest/start` returns 200.
TXLINE mint (Token-2022): `Zhw9TVKp68a1QrftncMSd6ELXKDtpVMNuMGr1jNwdeL`
Free tiers (price 0 tokens, verified vs on-chain PricingMatrix): service_level **1** (World Cup,
60s delay) and **12** (real-time). So subscribe needs only ~0.003 SOL (fees+rent), NO TXLINE tokens.
Accounts (from TxODDS docs example): pricing_matrix PDA["pricing_matrix"], token_treasury_pda
PDA["token_treasury_v2"], user/treasury ATAs via Token-2022. Client: `txline/live_mainnet.py`.
`--simulate` confirmed account derivations resolve to the real on-chain treasury vault.
Blocker: fund the generated keypair with ~0.01 SOL, then `--subscribe` → activate → live reads.
