"""
Paper comparison service.

Aggregates data for multiple KB papers and streams a comparative analysis
from a large language model (LLM).

LLM connection parameters (url, key, model) are read from the per-user
settings stored in the ``user_settings`` table (feature = "compare").
If the user has not configured them, the comparison is unavailable.
Other parameters (temperature, max_tokens, etc.) fall back to built-in
defaults defined in ``user_settings_service``.
"""

import json
import os
import sys
from typing import Generator, Optional

from openai import OpenAI

# ---------------------------------------------------------------------------
# Lazy service imports (avoid circular imports)
# ---------------------------------------------------------------------------

_kb_service = None
_data_service = None
_user_settings_service = None
_user_presets_service = None
_user_paper_service = None


def _get_kb_service():
    global _kb_service
    if _kb_service is None:
        from services import kb_service as _ks
        _kb_service = _ks
    return _kb_service


def _get_data_service():
    global _data_service
    if _data_service is None:
        from services import data_service as _ds
        _data_service = _ds
    return _data_service


def _get_user_paper_service():
    global _user_paper_service
    if _user_paper_service is None:
        from services import user_paper_service as _ups
        _user_paper_service = _ups
    return _user_paper_service


def _get_user_settings_service():
    global _user_settings_service
    if _user_settings_service is None:
        from services import user_settings_service as _us
        _user_settings_service = _us
    return _user_settings_service


def _get_user_presets_service():
    global _user_presets_service
    if _user_presets_service is None:
        from services import user_presets_service as _up
        _user_presets_service = _up
    return _user_presets_service


# ---------------------------------------------------------------------------
# file_collect directory
# ---------------------------------------------------------------------------

_SEVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FILE_COLLECT_DIR = os.path.join(_SEVER_ROOT, "data", "file_collect")


def _find_paper_dir(paper_id: str) -> Optional[str]:
    """Search all date directories under file_collect/ for a paper_id folder.
    Returns the absolute path to the paper directory, or None."""
    # Security: reject paper_id with path traversal characters
    if '..' in paper_id or '/' in paper_id or '\\' in paper_id or '\x00' in paper_id:
        return None
    if not os.path.isdir(_FILE_COLLECT_DIR):
        return None
    for date_dir in sorted(os.listdir(_FILE_COLLECT_DIR), reverse=True):
        paper_dir = os.path.join(_FILE_COLLECT_DIR, date_dir, paper_id)
        if os.path.isdir(paper_dir):
            return paper_dir
    return None


def _read_file(path: str) -> Optional[str]:
    """Read a text file, return None if it doesn't exist."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _load_source_content(paper_id: str, data_source: str) -> Optional[str]:
    """Load content for a paper based on the chosen data_source.

    data_source values:
      - "full_text": read {paper_id}_mineru.md from file_collect
      - "abstract":  read pdf_info.json -> abstract field
      - "summary":   read {paper_id}_summary.md from file_collect
    """
    paper_dir = _find_paper_dir(paper_id)
    if not paper_dir:
        return None

    if data_source == "full_text":
        path = os.path.join(paper_dir, f"{paper_id}_mineru.md")
        return _read_file(path)

    elif data_source == "abstract":
        path = os.path.join(paper_dir, "pdf_info.json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                info = json.load(f)
            return info.get("abstract") or None
        except Exception:
            return None

    elif data_source == "summary":
        path = os.path.join(paper_dir, f"{paper_id}_summary.md")
        return _read_file(path)

    return None


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _approx_tokens(text: str) -> int:
    # Use character count * 0.6 to better handle CJK text
    # (CJK chars are ~1 token each, ASCII words ~1.3 chars/token)
    return int(len(text) * 0.6) if text else 0


def _crop(text: str, budget: int) -> str:
    # budget is in tokens; convert back to char limit (inverse of 0.6 factor)
    char_limit = int(budget / 0.6)
    if len(text) <= char_limit:
        return text
    return text[:char_limit]


# ---------------------------------------------------------------------------
# KB data aggregation
# ---------------------------------------------------------------------------

def get_papers_for_compare(
    user_id: int,
    paper_ids: list[str],
    scope: str = "kb",
) -> list[dict]:
    """
    Fetch paper data for comparison.  For each paper_id:
      - If paper_id starts with 'up_' (user-uploaded paper): fetch from user_paper_service
      - If scope is 'mypapers' and paper_id does not start with 'up_': also try user_paper_service
      - Otherwise: fetch from KB + data_service (standard flow)

    Note: Routing is primarily based on paper_id prefix so that cross-library
    carts (mixing kb and mypapers entries) work correctly regardless of scope.
    """
    kb = _get_kb_service()
    ds = _get_data_service()
    ups = _get_user_paper_service()

    results: list[dict] = []
    for pid in paper_ids:
        entry: dict = {"paper_id": pid}

        # Always route by ID prefix first; fall back to scope for legacy behaviour
        is_user_paper = pid.startswith("up_") or scope == "mypapers"

        if is_user_paper:
            # Fetch from user_paper_service
            paper = ups.get_paper(user_id, pid)
            if paper:
                # Build paper_data compatible structure from user paper fields
                summary = None
                if paper.get("summary_json"):
                    try:
                        import json as _json
                        summary = _json.loads(paper["summary_json"])
                    except Exception:
                        summary = None

                paper_assets = None
                if paper.get("paper_assets_json"):
                    try:
                        import json as _json
                        paper_assets = _json.loads(paper["paper_assets_json"])
                    except Exception:
                        paper_assets = None

                entry["paper_data"] = {
                    "short_title": paper.get("title", ""),
                    "📖标题": paper.get("title", ""),
                    "abstract": paper.get("abstract", ""),
                    "institution": paper.get("institution", ""),
                    "🌐来源": paper.get("external_url", ""),
                    **(summary if isinstance(summary, dict) else {}),
                }
                entry["paper_assets"] = paper_assets
            else:
                entry["paper_data"] = {}
                entry["paper_assets"] = None
        else:
            # Standard KB flow
            paper_row = kb.get_paper_data(user_id, pid, scope)
            if paper_row:
                entry["paper_data"] = paper_row
            else:
                entry["paper_data"] = {}

            detail = ds.get_paper_detail(pid, user_id=user_id)
            if detail:
                entry["paper_assets"] = detail.get("paper_assets")
            else:
                entry["paper_assets"] = None

        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_user_content(
    papers: list[dict],
    data_source: str = "summary",
    compare_results: Optional[list[dict]] = None,
) -> str:
    """Serialize paper data (and optional historical compare reports) into the user prompt.

    When *data_source* is ``"full_text"`` or ``"summary"``, the content from
    the corresponding file in ``file_collect`` is used as the primary body for
    each paper.  When ``"abstract"``, only the original abstract from
    ``pdf_info.json`` is included.

    Basic metadata (paper_id, title, institution) is always prepended so the
    LLM can identify each paper regardless of which data source is chosen.

    If *compare_results* is provided, each item's markdown report is appended
    after the papers section as reference context for the LLM.
    """
    _DATA_SOURCE_LABELS = {
        "full_text": "全文",
        "abstract": "原文摘要",
        "summary": "系统总结",
    }

    parts: list[str] = []

    if papers:
        parts.append(f"[数据源: {_DATA_SOURCE_LABELS.get(data_source, data_source)}]\n")

        for i, p in enumerate(papers, 1):
            pd = p.get("paper_data", {})
            pid = p.get("paper_id", "unknown")
            parts.append(f"--- 论文 {i}: {pid} ---")
            parts.append(f"机构: {pd.get('institution', '未知')}")
            parts.append(f"短标题: {pd.get('short_title', '未知')}")
            parts.append(f"标题: {pd.get('📖标题', '')}")
            parts.append(f"来源: {pd.get('🌐来源', '')}")

            # -- Load content from the chosen data source -----------------------
            source_content = _load_source_content(pid, data_source)

            if source_content:
                parts.append(f"\n{source_content}")
            else:
                # Fallback: use whatever structured data is available from KB
                parts.append(f"（未找到 {_DATA_SOURCE_LABELS.get(data_source, data_source)} 数据，使用结构化摘要替代）")

                intro = pd.get("🛎️文章简介", {})
                if isinstance(intro, dict):
                    parts.append(f"研究问题: {intro.get('🔸研究问题', '')}")
                    parts.append(f"主要贡献: {intro.get('🔸主要贡献', '')}")

                methods = pd.get("📝重点思路", [])
                if methods:
                    parts.append("重点思路:")
                    for m in methods:
                        parts.append(f"  - {m}")

                findings = pd.get("🔎分析总结", [])
                if findings:
                    parts.append("分析总结:")
                    for f_ in findings:
                        parts.append(f"  - {f_}")

                opinion = pd.get("💡个人观点", "")
                if opinion:
                    parts.append(f"个人观点: {opinion}")

                abstract = pd.get("abstract", "")
                if abstract:
                    parts.append(f"摘要: {abstract}")

                # paper_assets blocks (if available)
                assets = p.get("paper_assets")
                if assets and isinstance(assets, dict):
                    blocks = assets.get("blocks", assets)
                    if isinstance(blocks, dict):
                        for key in ("background", "objective", "method", "data",
                                    "experiment", "metrics", "results", "limitations"):
                            block = blocks.get(key)
                            if block and isinstance(block, dict):
                                text = block.get("text", "")
                                bullets = block.get("bullets", [])
                                if text or bullets:
                                    parts.append(f"[{key}]:")
                                    if text:
                                        parts.append(f"  {text}")
                                    for b in bullets:
                                        parts.append(f"  - {b}")

            parts.append("")  # blank line between papers

    # -- Append historical compare reports as reference context ---------------
    if compare_results:
        parts.append("\n[以下是已保存的历史对比分析报告，供参考]\n")
        for j, cr in enumerate(compare_results, 1):
            title = cr.get("title", f"对比报告 {j}")
            markdown = cr.get("markdown", "")
            parts.append(f"--- 历史对比报告 {j}: 《{title}》 ---")
            if markdown:
                parts.append(markdown)
            parts.append("")

    return "\n".join(parts)


def get_compare_results_for_context(
    user_id: int,
    result_ids: list[int],
) -> list[dict]:
    """Fetch saved compare results to be used as reference context in a new analysis.

    Returns a list of dicts with ``id``, ``title``, and ``markdown`` fields.
    Results that do not belong to the user or do not exist are silently skipped.
    """
    kb = _get_kb_service()
    results: list[dict] = []
    for rid in result_ids:
        row = kb.get_compare_result(user_id, rid)
        if row:
            results.append({
                "id": row.get("id", rid),
                "title": row.get("title", ""),
                "markdown": row.get("markdown", ""),
            })
    return results


# ---------------------------------------------------------------------------
# Streaming generator
# ---------------------------------------------------------------------------

def stream_compare(
    user_id: int,
    paper_ids: list[str],
    scope: str = "kb",
    compare_result_ids: Optional[list[int]] = None,
) -> Generator[str, None, None]:
    """
    Generator that yields SSE-formatted strings:
        data: <chunk>\n\n
    with a final:
        data: [DONE]\n\n

    Supports cross-library comparison:
    - paper_ids may mix KB papers (any scope) and user-uploaded papers (up_* prefix)
    - compare_result_ids references saved compare reports whose markdown is
      appended to the prompt as reference context for the LLM

    LLM configuration is read from the user's personal settings
    (feature="compare").  If url/key/model are not configured the stream
    emits an error message and terminates.
    """
    # 0. Load user settings for the correct feature based on scope
    us = _get_user_settings_service()
    ups = _get_user_presets_service()
    feature = "inspiration" if scope == "inspiration" else "compare"
    # mypapers scope reuses the "compare" LLM configuration
    cfg = us.get_settings(user_id, feature)

    # If a preset is selected, override LLM connection params from preset
    llm_preset_id = cfg.get("llm_preset_id")
    if llm_preset_id:
        preset = ups.get_llm_preset(user_id, int(llm_preset_id))
        if preset:
            cfg["llm_base_url"] = preset.get("base_url", "")
            cfg["llm_api_key"] = preset.get("api_key", "")
            cfg["llm_model"] = preset.get("model", "")
            if preset.get("max_tokens") is not None:
                cfg["max_tokens"] = preset["max_tokens"]
            if preset.get("temperature") is not None:
                cfg["temperature"] = preset["temperature"]
            if preset.get("input_hard_limit") is not None:
                cfg["input_hard_limit"] = preset["input_hard_limit"]
            if preset.get("input_safety_margin") is not None:
                cfg["input_safety_margin"] = preset["input_safety_margin"]

    # If a prompt preset is selected, override system_prompt
    prompt_preset_id = cfg.get("prompt_preset_id")
    if prompt_preset_id:
        p_preset = ups.get_prompt_preset(user_id, int(prompt_preset_id))
        if p_preset and p_preset.get("prompt_content"):
            cfg["system_prompt"] = p_preset["prompt_content"]

    llm_url = (cfg.get("llm_base_url") or "").strip()
    llm_key = (cfg.get("llm_api_key") or "").strip()
    llm_model = (cfg.get("llm_model") or "").strip()

    if not llm_url or not llm_key or not llm_model:
        feature_label = "灵感涌现" if feature == "inspiration" else "对比分析"
        yield f"data: {json.dumps(f'请先在「个人中心 → {feature_label}」中配置 LLM 的 URL、API Key 和 Model，或选择一个模型预设。', ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    # 1. Aggregate paper data
    papers = get_papers_for_compare(user_id, paper_ids, scope) if paper_ids else []

    # 1b. Fetch saved compare results as reference context
    saved_results: list[dict] = []
    if compare_result_ids:
        saved_results = get_compare_results_for_context(user_id, compare_result_ids)

    if not papers and not saved_results:
        yield "data: 未找到对应的论文或对比报告数据。\n\n"
        yield "data: [DONE]\n\n"
        return

    # 2. Build prompt
    system_prompt = (cfg.get("system_prompt") or "").strip()
    if not system_prompt:
        # Fallback to default from user_settings_service
        defaults = us.get_defaults(feature)
        system_prompt = defaults.get("system_prompt", "")

    data_source = (cfg.get("data_source") or "summary").strip()
    if data_source not in ("full_text", "abstract", "summary"):
        data_source = "summary"

    user_content = _build_user_content(papers, data_source, compare_results=saved_results)

    # Token budget control
    hard_limit = int(cfg.get("input_hard_limit", 129024))
    safety_margin = int(cfg.get("input_safety_margin", 4096))
    limit_total = hard_limit - safety_margin
    sys_tokens = _approx_tokens(system_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = _crop(user_content, user_budget)

    # 3. Call LLM with streaming
    try:
        client = OpenAI(api_key=llm_key, base_url=llm_url)

        kwargs = {}
        temperature = cfg.get("temperature")
        if temperature is not None:
            kwargs["temperature"] = float(temperature)
        max_tokens = cfg.get("max_tokens")
        if max_tokens is not None:
            kwargs["max_tokens"] = min(int(max_tokens) * 2, 8192)

        response = client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            stream=True,
            **kwargs,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                yield f"data: {json.dumps(text, ensure_ascii=False)}\n\n"

    except Exception as exc:
        yield f"data: {json.dumps(f'分析失败: {exc}', ensure_ascii=False)}\n\n"

    yield "data: [DONE]\n\n"
