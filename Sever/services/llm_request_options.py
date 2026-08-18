"""
Build provider-specific extra kwargs for OpenAI-compatible chat.completions.create calls.

Usage::

    from services.llm_request_options import build_thinking_kwargs

    kwargs: dict = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    kwargs.update(build_thinking_kwargs(cfg))
    response = client.chat.completions.create(model=model, messages=msgs, **kwargs)

The helper only touches thinking-mode parameters.  temperature / max_tokens / stream
remain the caller's responsibility so existing call-site logic is undisturbed.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

_QWEN_URL_FRAGMENTS = (
    "dashscope.aliyuncs.com",
    "dashscope-intl.aliyuncs.com",
)

_QWEN_MODEL_PREFIXES = (
    "qwen",
    "qwq",
)

_DEEPSEEK_URL_FRAGMENTS = (
    "api.deepseek.com",
)


def _is_qwen(base_url: str, model: str) -> bool:
    """Return True when the endpoint/model is a Qwen/DashScope deployment."""
    url = (base_url or "").lower()
    mdl = (model or "").lower()
    if any(f in url for f in _QWEN_URL_FRAGMENTS):
        return True
    if any(mdl.startswith(p) for p in _QWEN_MODEL_PREFIXES):
        return True
    return False


def _is_direct_deepseek(base_url: str) -> bool:
    """Return True for the official DeepSeek OpenAI-compatible endpoint.

    Keep this URL-scoped rather than model-scoped: a DeepSeek model routed via
    another provider may not accept DeepSeek's vendor-specific ``thinking``
    request body.
    """
    url = (base_url or "").lower()
    return any(fragment in url for fragment in _DEEPSEEK_URL_FRAGMENTS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_thinking_kwargs(cfg: dict) -> dict:
    """Return extra kwargs to merge into chat.completions.create for thinking mode.

    Decision table
    ~~~~~~~~~~~~~~
    - Qwen/DashScope endpoint or model:
        enable_thinking=True  → extra_body={"enable_thinking": True}
        enable_thinking=False → extra_body={"enable_thinking": False}
      (Passing False explicitly turns off thinking on hybrid-mode models like Qwen3.)
    - Official DeepSeek endpoint:
        enable_thinking=True  → extra_body={"thinking": {"type": "enabled"}}
        enable_thinking=False → extra_body={"thinking": {"type": "disabled"}}
      DeepSeek V4 defaults to thinking mode, so ``False`` must be sent
      explicitly to preserve the configured output budget for final content.
    - All other providers: return {} — do not inject unknown parameters.

    The caller merges the returned dict into its existing kwargs::

        kwargs.update(build_thinking_kwargs(cfg))

    Args:
        cfg: The resolved LLM config dict.  Must contain at minimum:
             - "llm_base_url" or "base_url" (str)
             - "llm_model"    or "model"    (str)
             - "enable_thinking"            (bool | int, default False)
    """
    base_url: str = (cfg.get("llm_base_url") or cfg.get("base_url") or "").strip()
    model: str    = (cfg.get("llm_model")    or cfg.get("model")    or "").strip()
    enable: bool  = bool(cfg.get("enable_thinking", False))

    if _is_qwen(base_url, model):
        return {"extra_body": {"enable_thinking": enable}}

    if _is_direct_deepseek(base_url):
        return {
            "extra_body": {
                "thinking": {"type": "enabled" if enable else "disabled"}
            }
        }

    return {}
