"""
leadgen/llm.py — self-contained birleşik LLM katmanı.

kahhar/core/llm_client.py'den uyarlandı; config bağımlılığı kaldırıldı,
key'ler doğrudan ~/leadgen/.env (veya ortam değişkeni) üzerinden okunuyor.

Sağlayıcı önceliği (ilk key bulunan; hata olursa sonrakine düşer):
    1. Groq        (llama-3.3-70b-versatile) — ücretsiz
    2. OpenRouter  (deepseek/deepseek-chat) — fallback
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("leadgen.llm")

_OPENROUTER_EP = "https://openrouter.ai/api/v1/chat/completions"
_GROQ_EP = "https://api.groq.com/openai/v1/chat/completions"
_OPENROUTER_HEADERS = {"HTTP-Referer": "https://leadgen.local", "X-Title": "leadgen"}

# Serileştir: ücretsiz Groq TPM (~6000 tok/dk) limitini aşmamak için tek-tek.
_llm_semaphore = asyncio.Semaphore(1)
_last_call_time: float = 0.0
_rate_limit_lock = asyncio.Lock()

# Çağrılar arası min boşluk (TPM'e nefes aldır) ve 429 backoff denemeleri.
_MIN_GAP_SEC = 2.5
_MAX_429_RETRIES = 4


def _load_env() -> Dict[str, str]:
    """~/leadgen/.env dosyasını oku; ortam değişkenleri override eder."""
    env: Dict[str, str] = {}
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENROUTER_MODEL"):
        if os.getenv(k):
            env[k] = os.environ[k]
    return env


_ENV = _load_env()


def _providers() -> List[Tuple[str, str, str]]:
    provs: List[Tuple[str, str, str]] = []
    if _ENV.get("GROQ_API_KEY"):
        provs.append(("groq", _ENV["GROQ_API_KEY"], "llama-3.3-70b-versatile"))
    if _ENV.get("OPENROUTER_API_KEY"):
        provs.append(("openrouter", _ENV["OPENROUTER_API_KEY"],
                      _ENV.get("OPENROUTER_MODEL", "deepseek/deepseek-chat")))
    return provs


def active_provider() -> Optional[str]:
    provs = _providers()
    return provs[0][0] if provs else None


def available() -> bool:
    return bool(_providers())


async def _call_openai_compat(
    endpoint: str, api_key: str, model: str, messages: List[Dict[str, str]],
    temperature: float, max_tokens: int, json_mode: bool, timeout: int,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Tuple[str, Optional[str]]:
    """('ok', text) | ('rate_limit', None) | ('no_credit', None) | ('error', None)."""
    import httpx
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    body: Dict[str, Any] = {
        "model": model, "messages": messages,
        "temperature": temperature, "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(endpoint, headers=headers, json=body)
    if r.status_code == 200:
        return "ok", r.json()["choices"][0]["message"]["content"]
    if r.status_code == 429:
        return "rate_limit", None
    if r.status_code in (401, 402, 403):
        logger.debug(f"[LLM] {endpoint} → HTTP {r.status_code} (kredi/yetki): {r.text[:120]}")
        return "no_credit", None
    logger.warning(f"[LLM] {endpoint} → HTTP {r.status_code}: {r.text[:160]}")
    return "error", None


async def chat(
    prompt: str, *, system: Optional[str] = None, model: Optional[str] = None,
    temperature: float = 0.2, max_tokens: int = 1024, json_mode: bool = False,
    timeout: int = 60,
) -> Optional[str]:
    provs = _providers()
    if not provs:
        logger.debug("[LLM] Hiç API key yok — çağrı atlandı")
        return None

    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for name, key, default_model in provs:
        use_model = model or default_model
        endpoint = _OPENROUTER_EP if name == "openrouter" else _GROQ_EP
        extra = _OPENROUTER_HEADERS if name == "openrouter" else None

        for attempt in range(_MAX_429_RETRIES):
            # Global pacing: TPM'e nefes aldır
            global _last_call_time
            async with _rate_limit_lock:
                gap = time.monotonic() - _last_call_time
                if gap < _MIN_GAP_SEC:
                    await asyncio.sleep(_MIN_GAP_SEC - gap)
                _last_call_time = time.monotonic()
            try:
                async with _llm_semaphore:
                    status, text = await _call_openai_compat(
                        endpoint, key, use_model, messages,
                        temperature, max_tokens, json_mode, timeout, extra,
                    )
            except Exception as e:
                logger.debug(f"[LLM] {name} exception: {e}")
                break  # sonraki sağlayıcıya geç
            if status == "ok" and text:
                return text
            if status == "rate_limit":
                backoff = min(20.0, 4.0 * (attempt + 1))  # 4,8,12,16s
                logger.debug(f"[LLM] {name} 429 — {backoff}s backoff (deneme {attempt+1})")
                await asyncio.sleep(backoff)
                continue
            # no_credit / error → bu sağlayıcıyı bırak, sonrakine düş
            break
    return None


def _extract_json(text: str) -> Optional[Any]:
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
        if start >= 0:
            close_ch = "}" if text[start] == "{" else "]"
            end = text.rfind(close_ch) + 1
            if end > start:
                text = text[start:end]
    for candidate in (text, re.sub(r",\s*([}\]])", r"\1", text)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


async def chat_json(
    prompt: str, *, system: Optional[str] = None, model: Optional[str] = None,
    temperature: float = 0.1, max_tokens: int = 1024, timeout: int = 60,
) -> Optional[Any]:
    text = await chat(prompt, system=system, model=model, temperature=temperature,
                      max_tokens=max_tokens, json_mode=True, timeout=timeout)
    return _extract_json(text) if text else None
