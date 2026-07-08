"""
txline/client.py — TxLINE (TxODDS) data-layer client for the World Cup hackathon.

Auth flow (from docs):
  1. guest JWT:  POST {origin}/auth/guest/start            -> {token}
  2. on-chain subscribe (free tier, devnet, zero cost):    program.subscribe(level, weeks)
  3. activate:   sign "txSig:leagues:jwt" (Ed25519) ->
                 POST {api}/token/activate {txSig,walletSignature,leagues}  -> apiToken
  4. reads:      headers Authorization: Bearer {jwt} + X-Api-Token: {apiToken}

Endpoints:
  GET /api/fixtures/snapshot?competitionId=...
  GET /api/odds/snapshot/{fixtureId}
  GET /api/odds/updates/{epochDay}/{hourOfDay}/{interval}
  GET /api/scores/snapshot/{fixtureId}
  GET /api/scores/updates/{fixtureId}

Devnet:  origin=https://txline-dev.txodds.com  program=6pW64gN1s2uqjHkn1unFeEjAwJkPGHoppGvS715wyP2J
Mainnet: origin=https://txline.txodds.com      program=9ExbZjAapQww1vfcisDmrngPinHTEfpjYRWMunJgcKaA
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

DEVNET = {
    "origin": "https://txline-dev.txodds.com",
    "rpc": "https://api.devnet.solana.com",
    "program": "6pW64gN1s2uqjHkn1unFeEjAwJkPGHoppGvS715wyP2J",
}
MAINNET = {
    "origin": "https://txline.txodds.com",
    "rpc": "https://api.mainnet-beta.solana.com",
    "program": "9ExbZjAapQww1vfcisDmrngPinHTEfpjYRWMunJgcKaA",
}

_TOKENS = Path(__file__).resolve().parent.parent / "out" / "txline_tokens.json"


@dataclass
class TxLineClient:
    net: dict
    jwt: str = ""
    api_token: str = ""

    @property
    def origin(self) -> str:
        return self.net["origin"]

    # ── auth ────────────────────────────────────────────────────────────
    def guest_jwt(self) -> str:
        r = httpx.post(f"{self.origin}/auth/guest/start", json={}, timeout=20,
                       headers={"Content-Type": "application/json"})
        r.raise_for_status()
        self.jwt = r.json()["token"]
        return self.jwt

    def activation_message(self, tx_sig: str, leagues: list[int]) -> str:
        """Message that must be Ed25519-signed by the subscribing wallet."""
        return f"{tx_sig}:{','.join(str(x) for x in leagues)}:{self.jwt}"

    def activate(self, tx_sig: str, wallet_sig_b64: str, leagues: list[int]) -> str:
        r = httpx.post(f"{self.origin}/api/token/activate",
                       json={"txSig": tx_sig, "walletSignature": wallet_sig_b64,
                             "leagues": leagues},
                       headers={"Authorization": f"Bearer {self.jwt}",
                                "Content-Type": "application/json"}, timeout=30)
        r.raise_for_status()
        data = r.json()
        self.api_token = data.get("token") or data if isinstance(data, str) else data.get("token", "")
        self._save()
        return self.api_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.jwt}", "X-Api-Token": self.api_token,
                "Content-Type": "application/json"}

    def _save(self) -> None:
        _TOKENS.write_text(json.dumps({"jwt": self.jwt, "api_token": self.api_token,
                                       "net": self.net["origin"]}))

    def load_tokens(self) -> bool:
        if _TOKENS.exists():
            d = json.loads(_TOKENS.read_text())
            self.jwt, self.api_token = d.get("jwt", ""), d.get("api_token", "")
            return bool(self.api_token)
        return False

    # ── reads ───────────────────────────────────────────────────────────
    def _get(self, path: str) -> Any:
        r = httpx.get(f"{self.origin}/api/{path}", headers=self._headers(), timeout=30)
        if r.status_code != 200:
            return {"error": r.status_code, "body": r.text[:200]}
        return r.json()

    def fixtures(self, competition_id: Optional[int] = None) -> Any:
        q = f"?competitionId={competition_id}" if competition_id else ""
        return self._get(f"fixtures/snapshot{q}")

    def odds_snapshot(self, fixture_id: int) -> Any:
        return self._get(f"odds/snapshot/{fixture_id}")

    def odds_updates(self, epoch_day: int, hour: int, interval: int) -> Any:
        return self._get(f"odds/updates/{epoch_day}/{hour}/{interval}")

    def scores_snapshot(self, fixture_id: int) -> Any:
        return self._get(f"scores/snapshot/{fixture_id}")

    def scores_updates(self, fixture_id: int) -> Any:
        return self._get(f"scores/updates/{fixture_id}")


def devnet() -> TxLineClient:
    return TxLineClient(DEVNET)
