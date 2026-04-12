"""
Auto-Classify Service

Automatically classifies newly saved KB papers into user-defined folders
using a single LLM call.

Design
------
- User defines a list of folders (name + description) in advanced settings
  (feature='auto_classify').
- When a paper is added to the KB without an explicit folder_id, and
  auto-classify is enabled, `enqueue_classify` is called.
- The paper's classify_status is set to 'pending' immediately.
- A daemon background thread reads the queue and calls the LLM to decide
  which folder the paper belongs to (or '未分类' if confidence is too low).
- The paper's folder_id is updated in-place; the classify status is set to
  'done' or 'failed'.

Concurrency
-----------
- A BoundedSemaphore limits simultaneous LLM calls to MAX_CONCURRENT_CLASSIFY
  threads, preventing runaway resource usage when reclassify-all is triggered
  on a large library.

This reuses the same threading + _running_jobs pattern used by
kb_pipeline_service and user_paper_pipeline_service.
"""

import json
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_running_jobs: set[str] = set()  # "user_id:paper_id:scope"
_running_lock = threading.Lock()

MAX_CONCURRENT_CLASSIFY = 5
_classify_semaphore = threading.BoundedSemaphore(MAX_CONCURRENT_CLASSIFY)

_UNCLASSIFIED_FOLDER_NAME = "未分类"

_CLASSIFY_PROMPT = """\
你是一个论文自动分类助手。用户已定义了以下知识库目录结构（编号、完整路径和描述）：

{folder_list}

请根据下面的论文信息，判断这篇论文最适合放入哪个目录。
- 优先选择叶子目录（最具体的分类），而非父目录。
- 如果置信度不足或所有目录都不适合，请回答「未分类」。

论文信息：
- 标题：{title}
- arXiv 分类：{categories}
- 作者：{authors}
- 机构：{institution}
- 研究问题：{research_question}
- 主要贡献：{contribution}
- 摘要：{abstract}

请严格按照以下 JSON 格式返回，不要有任何额外文字：
{{"folder": "完整路径（必须与上面列出的完整路径完全一致，或为「未分类」）", "confidence": 0.85, "reason": "一句话说明分类原因"}}
"""


# ---------------------------------------------------------------------------
# Job tracking helpers
# ---------------------------------------------------------------------------

def _job_key(user_id: int, paper_id: str, scope: str) -> str:
    return f"{user_id}:{paper_id}:{scope}"


def _mark_running(key: str) -> bool:
    with _running_lock:
        if key in _running_jobs:
            return False
        _running_jobs.add(key)
        return True


def _mark_done(key: str) -> None:
    with _running_lock:
        _running_jobs.discard(key)


def is_classifying(user_id: int, paper_id: str, scope: str = "kb") -> bool:
    return _job_key(user_id, paper_id, scope) in _running_jobs


# ---------------------------------------------------------------------------
# LLM resolution
# ---------------------------------------------------------------------------

def _resolve_llm_config(user_id: int) -> Optional[dict]:
    """
    Read auto_classify feature settings and resolve the LLM connection config.
    Returns dict with keys: base_url, api_key, model, max_tokens, temperature.
    Returns None if not configured.
    """
    from services import user_settings_service as uss
    from services import user_presets_service as ups

    cfg = uss.get_settings(user_id, "auto_classify")
    if not cfg.get("enabled"):
        return None

    llm_preset_id = cfg.get("llm_preset_id")
    if llm_preset_id:
        try:
            preset = ups.get_llm_preset(user_id, int(llm_preset_id))
        except Exception:
            preset = None
        if preset:
            return {
                "base_url": preset.get("base_url", ""),
                "api_key": preset.get("api_key", ""),
                "model": preset.get("model", ""),
                "max_tokens": preset.get("max_tokens") or 512,
                "temperature": preset.get("temperature") if preset.get("temperature") is not None else 0.1,
            }

    # Fallback: direct config (llm_base_url / llm_api_key / llm_model stored directly)
    base_url = (cfg.get("llm_base_url") or "").strip()
    api_key = (cfg.get("llm_api_key") or "").strip()
    model = (cfg.get("llm_model") or "").strip()
    if not (base_url and api_key and model):
        return None

    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "max_tokens": cfg.get("max_tokens") or 512,
        "temperature": cfg.get("temperature") if cfg.get("temperature") is not None else 0.1,
    }


# ---------------------------------------------------------------------------
# Folder path helpers (multi-level support)
# ---------------------------------------------------------------------------

def _build_full_paths(settings_folders: list) -> dict:
    """
    Returns {folder_id: full_path} for all synced folders.
    Full path: "ParentName/ChildName" for nested, just "Name" for roots.
    Unsynced folders (no folder_id) are excluded.
    """
    by_id = {f["folder_id"]: f for f in settings_folders if f.get("folder_id")}
    cache: dict = {}

    def get_path(fid: int, visited: set | None = None) -> str:
        if fid in cache:
            return cache[fid]
        if visited is None:
            visited = set()
        if fid in visited:
            return by_id.get(fid, {}).get("name", "")
        visited.add(fid)
        f = by_id[fid]
        parent_id = f.get("parent_id")
        if parent_id and parent_id in by_id:
            parent_path = get_path(parent_id, visited)
            path = f"{parent_path}/{f['name']}" if parent_path else f["name"]
        else:
            path = f["name"]
        cache[fid] = path
        return path

    return {fid: get_path(fid) for fid in by_id}


def _build_folder_tree_text(settings_folders: list) -> str:
    """
    Build a numbered, indented folder list for the LLM prompt.
    Shows full paths so multi-level hierarchies are unambiguous.
    Example:
        1. NLP — 自然语言处理
          2. NLP/大模型推理优化 — KV cache, speculative decoding
          3. NLP/RLHF — 人类反馈强化学习
        4. CV — 计算机视觉
    """
    if not settings_folders:
        return "(未配置任何目录)"

    by_id = {f["folder_id"]: f for f in settings_folders if f.get("folder_id")}
    full_paths = _build_full_paths(settings_folders)

    # Build children map for tree traversal
    children_map: dict = {}
    roots = []
    for f in settings_folders:
        parent_id = f.get("parent_id")
        if parent_id and parent_id in by_id:
            children_map.setdefault(parent_id, []).append(f)
        else:
            roots.append(f)

    lines = []
    counter = [0]

    def dfs(folders: list, depth: int) -> None:
        for f in folders:
            counter[0] += 1
            fid = f.get("folder_id")
            path = full_paths.get(fid, f["name"]) if fid else f["name"]
            indent = "  " * depth
            desc = (f.get("description") or "").strip() or "（无描述）"
            lines.append(f"{indent}{counter[0]}. {path} — {desc}")
            children = children_map.get(fid, [])
            if children:
                dfs(children, depth + 1)

    dfs(roots, 0)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Folder resolution: map path/name -> real folder_id, creating if needed
# ---------------------------------------------------------------------------

def _resolve_or_create_folder(user_id: int, folder_path: str, scope: str, settings_folders: list) -> Optional[int]:
    """
    Given a folder path (e.g., "NLP/大模型推理优化") or plain name returned by
    the LLM, find the matching KB folder.
    Resolution order:
      1. Exact full-path match against precomputed full_paths.
      2. Leaf-name match (in case LLM omitted the parent prefix).
      3. Plain name match in settings (backward compat).
      4. get_or_create by leaf name (root-level fallback).
    """
    import services.kb_service as kbs

    if not folder_path or folder_path == _UNCLASSIFIED_FOLDER_NAME:
        return kbs.get_or_create_system_folder(user_id, _UNCLASSIFIED_FOLDER_NAME, scope)

    # Build full path -> folder_id mapping
    full_paths = _build_full_paths(settings_folders)
    path_to_id = {path: fid for fid, path in full_paths.items()}

    # 1. Exact full-path match
    if folder_path in path_to_id:
        return int(path_to_id[folder_path])

    # 2. Leaf-name match (e.g., LLM returned "大模型推理优化" without parent prefix)
    leaf = folder_path.split("/")[-1].strip()
    for fid, path in full_paths.items():
        if path.split("/")[-1] == leaf:
            return int(fid)

    # 3. Plain name match in settings (unsynced folder that has a folder_id)
    for sf in settings_folders:
        if sf.get("name") == leaf:
            fid = sf.get("folder_id")
            if fid:
                return int(fid)

    # 4. Root-level fallback
    return kbs.get_or_create_system_folder(user_id, leaf, scope)


# ---------------------------------------------------------------------------
# Core classification logic
# ---------------------------------------------------------------------------

def _do_classify(user_id: int, paper_id: str, scope: str = "kb") -> None:
    """Synchronous classification — called from a background thread."""
    import services.kb_service as kbs

    def _set(status: str, folder_id: Optional[int] = None,
             confidence: Optional[float] = None, error: str = "",
             reason: str = "") -> None:
        kbs.set_classify_status(
            user_id, paper_id,
            status=status, folder_id=folder_id,
            confidence=confidence, error=error, reason=reason,
            scope=scope,
        )

    try:
        from services import user_settings_service as uss
        from openai import OpenAI

        cfg = uss.get_settings(user_id, "auto_classify")
        if not cfg.get("enabled"):
            _set("skipped")
            return

        settings_folders: list = cfg.get("folders") or []
        if not settings_folders:
            _set("skipped", error="未配置分类目录")
            return

        confidence_threshold: float = float(cfg.get("confidence_threshold") or 0.6)

        llm_cfg = _resolve_llm_config(user_id)
        if llm_cfg is None:
            _set("failed", error="未配置 LLM 模型")
            return

        # Fetch paper data from KB using the shared connection helper
        conn = kbs._connect()
        conn_row = None
        try:
            conn_row = conn.execute(
                "SELECT paper_data FROM kb_papers WHERE user_id=? AND paper_id=? AND scope=?",
                (user_id, paper_id, scope),
            ).fetchone()
        finally:
            conn.close()

        if conn_row is None:
            _set("failed", error="论文不在知识库中")
            return

        try:
            paper_data = json.loads(conn_row["paper_data"])
        except Exception:
            paper_data = {}

        # Extract classification-relevant fields
        title = (
            paper_data.get("📖标题")
            or paper_data.get("short_title")
            or paper_id
        )
        intro = paper_data.get("🛎️文章简介") or {}
        research_question = intro.get("🔸研究问题", "") if isinstance(intro, dict) else ""
        contribution = intro.get("🔸主要贡献", "") if isinstance(intro, dict) else ""
        abstract = paper_data.get("abstract") or paper_data.get("推荐理由") or ""

        # Extra signals: arXiv categories, authors, institution
        categories_raw = paper_data.get("categories") or paper_data.get("arxiv_categories") or ""
        if isinstance(categories_raw, list):
            categories = ", ".join(categories_raw)
        else:
            categories = str(categories_raw).strip() or "（未提供）"

        authors_raw = paper_data.get("authors") or paper_data.get("author") or ""
        if isinstance(authors_raw, list):
            authors = "; ".join(str(a) for a in authors_raw[:5])
            if len(authors_raw) > 5:
                authors += f" 等 {len(authors_raw)} 位"
        else:
            authors = str(authors_raw).strip() or "（未提供）"

        institution = (paper_data.get("institution") or "（未提供）").strip() or "（未提供）"

        # Build hierarchical folder list for prompt
        folder_list_text = _build_folder_tree_text(settings_folders)
        full_paths = _build_full_paths(settings_folders)

        # Resolve custom prompt template from prompt preset (if configured)
        prompt_template = _CLASSIFY_PROMPT
        prompt_preset_id = cfg.get("prompt_preset_id")
        if prompt_preset_id:
            from services import user_presets_service as ups
            p_preset = ups.get_prompt_preset(user_id, int(prompt_preset_id))
            if p_preset and p_preset.get("prompt_content"):
                prompt_template = p_preset["prompt_content"]

        try:
            prompt_text = prompt_template.format(
                folder_list=folder_list_text,
                title=title,
                categories=categories,
                authors=authors,
                institution=institution,
                research_question=research_question or "（未提供）",
                contribution=contribution or "（未提供）",
                abstract=(abstract or "（未提供）")[:600],
            )
        except (KeyError, IndexError):
            logger.warning(
                "auto_classify: custom prompt template format error for %s, falling back to default",
                paper_id,
            )
            prompt_text = _CLASSIFY_PROMPT.format(
                folder_list=folder_list_text,
                title=title,
                categories=categories,
                authors=authors,
                institution=institution,
                research_question=research_question or "（未提供）",
                contribution=contribution or "（未提供）",
                abstract=(abstract or "（未提供）")[:600],
            )

        # Acquire semaphore to cap concurrent LLM calls
        _set("running")
        with _classify_semaphore:
            client = OpenAI(
                base_url=llm_cfg["base_url"],
                api_key=llm_cfg["api_key"],
            )
            response = client.chat.completions.create(
                model=llm_cfg["model"],
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=llm_cfg["max_tokens"],
                temperature=llm_cfg["temperature"],
            )
        raw = response.choices[0].message.content or ""

        # Parse JSON response
        try:
            # Strip markdown code fences if present
            stripped = raw.strip()
            if stripped.startswith("```"):
                stripped = "\n".join(stripped.split("\n")[1:])
                stripped = stripped.rstrip("`").strip()
            result = json.loads(stripped)
            folder_name: str = result.get("folder", _UNCLASSIFIED_FOLDER_NAME)
            confidence: float = float(result.get("confidence", 0.0))
            reason: str = result.get("reason", "")
        except Exception as parse_err:
            logger.warning("auto_classify: JSON parse error for %s: %s — raw=%r", paper_id, parse_err, raw)
            _set("failed", error=f"LLM 返回格式错误: {raw[:200]}")
            return

        # Valid values: leaf names, full paths, and the catch-all
        valid_names = {sf["name"] for sf in settings_folders} | set(full_paths.values()) | {_UNCLASSIFIED_FOLDER_NAME}
        if folder_name not in valid_names:
            logger.info(
                "auto_classify: LLM returned unknown folder %r for %s, falling back to 未分类",
                folder_name, paper_id
            )
            folder_name = _UNCLASSIFIED_FOLDER_NAME
            confidence = 0.0

        # If confidence below threshold, send to 未分类
        if confidence < confidence_threshold and folder_name != _UNCLASSIFIED_FOLDER_NAME:
            logger.info(
                "auto_classify: confidence %.2f below threshold %.2f for %s (%s → 未分类)",
                confidence, confidence_threshold, paper_id, folder_name
            )
            folder_name = _UNCLASSIFIED_FOLDER_NAME

        target_folder_id = _resolve_or_create_folder(user_id, folder_name, scope, settings_folders)

        # Move the paper to the resolved folder
        kbs.move_papers(user_id, [paper_id], target_folder_id, scope=scope)

        logger.info(
            "auto_classify: %s -> folder=%r (id=%s) confidence=%.2f reason=%r",
            paper_id, folder_name, target_folder_id, confidence, reason
        )
        _set("done", folder_id=target_folder_id, confidence=confidence, reason=reason)

    except Exception as exc:
        logger.exception("auto_classify: unhandled error for user=%s paper=%s: %s", user_id, paper_id, exc)
        try:
            import services.kb_service as kbs2
            kbs2.set_classify_status(
                user_id, paper_id,
                status="failed", error=str(exc)[:500],
                scope=scope,
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enqueue_classify(user_id: int, paper_id: str, scope: str = "kb") -> bool:
    """
    Mark a paper as pending classification and launch a daemon thread.
    Returns True if the job was enqueued, False if already running.
    """
    import services.kb_service as kbs

    key = _job_key(user_id, paper_id, scope)
    if not _mark_running(key):
        return False  # Already running

    # Mark as pending immediately so the UI can show it
    kbs.set_classify_status(user_id, paper_id, status="pending", scope=scope)

    def _worker():
        try:
            _do_classify(user_id, paper_id, scope)
        finally:
            _mark_done(key)

    t = threading.Thread(target=_worker, daemon=True, name=f"auto_classify_{paper_id}")
    t.start()
    return True


def enqueue_reclassify_all(user_id: int, scope: str = "kb") -> int:
    """
    Re-enqueue all papers in the KB for classification.
    Returns the number of papers enqueued.
    """
    import services.kb_service as kbs

    tree = kbs.get_tree(user_id, scope=scope)
    paper_ids: list[str] = []

    def _collect(folder: dict) -> None:
        for p in folder.get("papers") or []:
            paper_ids.append(p["paper_id"])
        for child in folder.get("children") or []:
            _collect(child)

    for p in tree.get("papers") or []:
        paper_ids.append(p["paper_id"])
    for folder in tree.get("folders") or []:
        _collect(folder)

    count = 0
    for pid in paper_ids:
        if enqueue_classify(user_id, pid, scope):
            count += 1
    return count


def sync_folders(user_id: int, folders_def: list, scope: str = "kb") -> list:
    """
    Synchronise the folder definition list with actual KB folders.

    Processes entries in the provided order (callers should send DFS order:
    parent before children).  Supports ``_key`` / ``_parent_key`` fields so
    that newly-created parent folders can be referenced by children in the
    same batch — even before the parent has a real ``folder_id``.

    Returns the updated folders_def list with ``folder_id`` filled in.
    """
    import services.kb_service as kbs

    updated = []
    # Maps _key -> resolved folder_id for within-batch parent resolution
    key_to_id: dict[str, int] = {}

    for entry in folders_def:
        name = (entry.get("name") or "").strip()
        if not name:
            continue

        existing_id = entry.get("folder_id") or None

        # Resolve parent_id:
        #  1. Use explicit parent_id if provided (already-synced parent).
        #  2. Fall back to _parent_key look-up in the current batch.
        parent_id = entry.get("parent_id") or None
        parent_key = entry.get("_parent_key") or None
        if not parent_id and parent_key and parent_key in key_to_id:
            parent_id = key_to_id[parent_key]

        if existing_id:
            # Verify the folder still exists in DB
            conn = kbs._connect()
            try:
                row = conn.execute(
                    "SELECT id FROM kb_folders WHERE id=? AND user_id=? AND scope=?",
                    (existing_id, user_id, scope)
                ).fetchone()
            finally:
                conn.close()
            if row:
                result_entry = {**entry, "folder_id": existing_id, "parent_id": parent_id}
                updated.append(result_entry)
                _key = entry.get("_key")
                if _key:
                    key_to_id[_key] = existing_id
                continue
            # Folder was deleted — fall through to re-create

        # Create or find the folder
        folder = kbs.create_folder(user_id, name, parent_id=parent_id, scope=scope)
        result_entry = {**entry, "folder_id": folder["id"], "parent_id": parent_id}
        updated.append(result_entry)
        _key = entry.get("_key")
        if _key:
            key_to_id[_key] = folder["id"]

    return updated


def recover_all_stalled_jobs() -> int:
    """
    Called once at server startup to re-enqueue papers whose classify_status
    was left as 'pending' or 'running' due to a previous server crash/restart.
    Returns the number of jobs re-enqueued.
    """
    import services.kb_service as kbs

    stalled = kbs.get_stalled_classify_papers(scope="kb")
    count = 0
    for entry in stalled:
        try:
            if enqueue_classify(entry["user_id"], entry["paper_id"], entry["scope"]):
                count += 1
        except Exception:
            logger.exception(
                "auto_classify: failed to re-enqueue stalled job user=%s paper=%s",
                entry["user_id"], entry["paper_id"],
            )
    if count:
        logger.info("auto_classify: re-enqueued %d stalled jobs on startup", count)
    return count
