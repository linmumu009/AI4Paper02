"""
LLM Client Factory — OpenRouter Key 池轮换的统一入口。

使用方法
--------
只需把原来的 ``OpenAI(api_key=key, base_url=base)`` 替换为::

    from services.llm_client_factory import build_llm_client

    client = build_llm_client(cfg)
    client.chat.completions.create(...)   # 池模式下：每次请求独立计数

其中 ``cfg`` 是现有各服务里的 LLM 配置字典，识别以下 key：
    - llm_api_key  / api_key                — API Key（普通模式）
    - llm_base_url / base_url               — API Base URL
    - use_openrouter_free_pool              — 布尔/整数，为真时从全局池轮换
    - llm_use_openrouter_free_pool          — 同上（备用字段名）
    - llm_model    / model                  — 模型名称

当启用 Key 池时，build_llm_client 返回一个轻量包装器：
- 每次调用 chat.completions.create 前，重新从池中选取今日用量最低的可用 Key；
- 立即将该 Key 的今日用量 +1（OpenRouter 在请求发出时即消耗免费配额）；
- 用该 Key 向 OpenRouter API 发起实际请求；
- 一个任务调用多轮模型时，每轮独立计数，计数准确反映实际消耗。

has_llm_credentials(cfg) 用于判断配置是否足够驱动一次 LLM 调用（池模式下
api_key 可为空）。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional

from openai import OpenAI

from services.network_target_guard import validate_user_llm_base_url

_logger = logging.getLogger("llm_client_factory")

_OPENROUTER_DEFAULT_BASE = "https://openrouter.ai/api/v1"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def has_llm_credentials(cfg: Dict[str, Any]) -> bool:
    """Return True when cfg carries enough info to issue at least one LLM call.

    In pool mode the api_key may be empty; a model name is still required.
    """
    model = (cfg.get("llm_model") or cfg.get("model") or "").strip()
    key = (cfg.get("llm_api_key") or cfg.get("api_key") or "").strip()
    use_pool = bool(
        cfg.get("use_openrouter_free_pool") or cfg.get("llm_use_openrouter_free_pool")
    )
    return bool(model and (key or use_pool))


def _should_apply_rate_limit(cfg: Dict[str, Any], kwargs: Dict[str, Any]) -> bool:
    use_pool = bool(
        cfg.get("use_openrouter_free_pool") or cfg.get("llm_use_openrouter_free_pool")
    )
    if use_pool:
        return True
    model = (kwargs.get("model") or cfg.get("model") or cfg.get("llm_model") or "")
    return ":free" in str(model)


def _create_with_rate_limit(
    cfg: Dict[str, Any],
    kwargs: Dict[str, Any],
    invoke: Callable[[], Any],
    *,
    on_rate_limit: Optional[Callable[[], None]] = None,
) -> Any:
    from services.openrouter_rate_limit import (
        OpenRouterRateLimitExhausted,
        compute_429_wait,
        extract_retry_wait_from_exception,
        is_rate_limit_error,
        wait_for_openrouter_slot,
    )
    from config.config import OPENROUTER_429_MAX_RETRIES

    apply_limit = _should_apply_rate_limit(cfg, kwargs)
    max_retries = max(1, int(OPENROUTER_429_MAX_RETRIES))

    for attempt in range(1, max_retries + 1):
        if apply_limit:
            wait_for_openrouter_slot()
        try:
            return invoke()
        except Exception as exc:
            if not apply_limit or not is_rate_limit_error(exc):
                raise
            if on_rate_limit:
                try:
                    on_rate_limit()
                except Exception as cb_exc:
                    _logger.warning("on_rate_limit callback failed: %s", cb_exc)
            if attempt >= max_retries:
                raise OpenRouterRateLimitExhausted(str(exc)) from exc
            retry_hint = extract_retry_wait_from_exception(exc)
            wait = compute_429_wait(attempt, retry_hint)
            _logger.warning(
                "OpenRouter 429 (attempt %d/%d); waiting %.1fs before retry: %s",
                attempt, max_retries, wait, exc,
            )
            time.sleep(wait)


def build_llm_client(cfg: Dict[str, Any]) -> OpenAI:
    """Return an OpenAI-compatible client for *cfg*."""
    use_pool = bool(
        cfg.get("use_openrouter_free_pool") or cfg.get("llm_use_openrouter_free_pool")
    )

    raw_base_url = (cfg.get("llm_base_url") or cfg.get("base_url") or "").strip()
    base_url = validate_user_llm_base_url(raw_base_url) or None

    if use_pool:
        pool_base_url = base_url or _OPENROUTER_DEFAULT_BASE
        return _PoolClient(pool_base_url, cfg)

    api_key = (cfg.get("llm_api_key") or cfg.get("api_key") or "").strip()
    client = OpenAI(api_key=api_key, base_url=base_url)
    if _should_apply_rate_limit(cfg, {}):
        return _DirectRateLimitedClient(client, cfg)
    return client


# ---------------------------------------------------------------------------
# Rate-limited wrappers
# ---------------------------------------------------------------------------

class _RateLimitedCompletions:
    def __init__(self, cfg: Dict[str, Any], invoke: Callable[..., Any]) -> None:
        self._cfg = cfg
        self._invoke = invoke

    def create(self, *args: Any, **kwargs: Any) -> Any:
        return _create_with_rate_limit(
            self._cfg,
            kwargs,
            lambda: self._invoke(*args, **kwargs),
            on_rate_limit=getattr(self, "_on_rate_limit", None),
        )


class _RateLimitedChat:
    def __init__(self, completions: _RateLimitedCompletions) -> None:
        self.completions = completions


class _DirectRateLimitedClient:
    """Wraps a real OpenAI client with free-tier RPM limiting."""

    def __init__(self, client: OpenAI, cfg: Dict[str, Any]) -> None:
        self._client = client
        self._cfg = cfg
        self.chat = _RateLimitedChat(
            _RateLimitedCompletions(cfg, client.chat.completions.create)
        )


# ---------------------------------------------------------------------------
# Pool-mode wrapper
# ---------------------------------------------------------------------------

class _PoolCompletions(_RateLimitedCompletions):
    """Picks a fresh pool key and increments usage counter before every request."""

    def __init__(self, pool_base_url: str, cfg: Dict[str, Any]) -> None:
        self._base_url = pool_base_url
        self._cfg = cfg
        self._last_key_id: Optional[int] = None
        super().__init__(cfg, self._pool_create)

    def _on_rate_limit(self) -> None:
        if self._last_key_id is None:
            return
        try:
            from services import openrouter_key_pool_service as _pool_svc
            from config.config import OPENROUTER_429_BASE_WAIT

            _pool_svc.mark_key_cooldown(self._last_key_id, float(OPENROUTER_429_BASE_WAIT))
        except Exception as exc:
            _logger.warning("_PoolCompletions: mark_key_cooldown failed: %s", exc)

    def _pool_create(self, *args: Any, **kwargs: Any) -> Any:
        from services import openrouter_key_pool_service as _pool_svc

        key_info = _pool_svc.select_available_key()
        self._last_key_id = key_info["id"]
        try:
            _pool_svc.record_success(key_info["id"])
        except Exception as exc:
            _logger.warning("_PoolCompletions.create: failed to record pool usage: %s", exc)

        real_client = OpenAI(api_key=key_info["api_key"], base_url=self._base_url)
        return real_client.chat.completions.create(*args, **kwargs)

    def create(self, *args: Any, **kwargs: Any) -> Any:
        return _create_with_rate_limit(
            self._cfg,
            kwargs,
            lambda: self._pool_create(*args, **kwargs),
            on_rate_limit=self._on_rate_limit,
        )


class _PoolChat:
    def __init__(self, completions: _PoolCompletions) -> None:
        self.completions = completions


class _PoolClient:
    """Drop-in replacement for ``OpenAI`` in pool mode."""

    def __init__(self, pool_base_url: str, cfg: Dict[str, Any]) -> None:
        self.chat = _PoolChat(_PoolCompletions(pool_base_url, cfg))
        self._cfg = cfg
