"""
Deep Research Q&A service.

Provides a multi-round, progressive-depth Q&A workflow over a batch of KB papers.

Workflow:
  Round 1 — Relevance ranking: LLM scores every selected paper against the user
    question using only abstract / AI summary.  Top N papers are selected.
  Round 2 — Summary analysis: LLM tries to answer the question from the AI
    summaries of the top N papers.  If the summaries are insufficient, it
    declares which papers need a full-text read.
  Round 3 — Full-text deep read (optional): The mineru-parsed Markdown of the
    requested papers is loaded (with token-budget control) and the LLM produces
    a final answer.

All rounds emit structured SSE events so the frontend can render each round
progressively:

  data: {"type":"round_start", "round":1, ...}
  data: {"type":"relevance_result", "round":1, "rankings":[...]}
  data: {"type":"round_start", "round":2, ...}
  data: {"type":"text", "round":2, "content":"..."}   ← streaming
  data: {"type":"round_done", "round":2, "action":"read_full", "papers":["id1",...]}
  data: {"type":"round_start", "round":3, ...}
  data: {"type":"text", "round":3, "content":"..."}   ← streaming
  data: {"type":"final_answer"}
  data: [DONE]

LLM connection parameters are read from the per-user settings stored in the
``user_settings`` table (feature = "deep_research"; falls back to "paper_chat"
if no model is configured for "deep_research").
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Generator, Optional

from openai import OpenAI
from openai import APIConnectionError, AuthenticationError, RateLimitError, APIStatusError
from services.llm_utils import approx_tokens as _approx_tokens, crop as _crop
from services import paper_data_utils as _pdu

# ---------------------------------------------------------------------------
# Lazy service imports (avoid circular imports)
# ---------------------------------------------------------------------------

_user_settings_service = None
_user_presets_service = None
_compare_service = None


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


def _get_compare_service():
    global _compare_service
    if _compare_service is None:
        from services import compare_service as _cs
        _compare_service = _cs
    return _compare_service


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Create research tables if they do not exist."""
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_sessions (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id           INTEGER NOT NULL,
                question          TEXT    NOT NULL,
                paper_ids_json    TEXT    NOT NULL,
                config_json       TEXT    NOT NULL DEFAULT '{}',
                parent_session_id INTEGER,
                status            TEXT    NOT NULL DEFAULT 'pending',
                created_at        TEXT    NOT NULL,
                updated_at        TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_research_sessions_user
                ON research_sessions(user_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS research_rounds (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      INTEGER NOT NULL
                                    REFERENCES research_sessions(id) ON DELETE CASCADE,
                round_number    INTEGER NOT NULL,
                round_type      TEXT    NOT NULL,
                input_paper_ids TEXT    NOT NULL DEFAULT '[]',
                output_json     TEXT    NOT NULL DEFAULT '{}',
                status          TEXT    NOT NULL DEFAULT 'pending',
                created_at      TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_research_rounds_session
                ON research_rounds(session_id, round_number);
            """
        )
        conn.commit()
        # Migrate: add parent_session_id column if this is an existing DB
        try:
            conn.execute("ALTER TABLE research_sessions ADD COLUMN parent_session_id INTEGER")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        # Migrate: add saved column for user-starred sessions
        try:
            conn.execute("ALTER TABLE research_sessions ADD COLUMN saved INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        # Migrate: add folder_id for folder-based organisation
        try:
            conn.execute("ALTER TABLE research_sessions ADD COLUMN folder_id INTEGER DEFAULT NULL")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Session CRUD helpers
# ---------------------------------------------------------------------------

def create_session(user_id: int, question: str, paper_ids: list[str], config: dict,
                   parent_session_id: Optional[int] = None) -> int:
    """Insert a new running session.  Uses an explicit transaction to minimise the
    race window between the has_running_session guard and this insert."""
    now = _now_iso()
    conn = _connect()
    try:
        with conn:  # BEGIN / COMMIT / ROLLBACK handled by context manager
            existing = conn.execute(
                "SELECT id FROM research_sessions WHERE user_id = ? AND status = 'running' LIMIT 1",
                (user_id,),
            ).fetchone()
            if existing:
                raise RuntimeError("concurrent running session detected")
            cur = conn.execute(
                "INSERT INTO research_sessions "
                "(user_id, question, paper_ids_json, config_json, parent_session_id, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'running', ?, ?)",
                (user_id, question, json.dumps(paper_ids, ensure_ascii=False),
                 json.dumps(config, ensure_ascii=False), parent_session_id, now, now),
            )
        return cur.lastrowid
    finally:
        conn.close()


def update_session_status(session_id: int, status: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE research_sessions SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now_iso(), session_id),
        )
        conn.commit()
    finally:
        conn.close()


def _touch_session(session_id: int) -> None:
    """Refresh updated_at so stale-session cleanup does not misfire on long-running jobs."""
    conn = _connect()
    try:
        conn.execute(
            "UPDATE research_sessions SET updated_at = ? WHERE id = ?",
            (_now_iso(), session_id),
        )
        conn.commit()
    finally:
        conn.close()


def save_round(session_id: int, round_number: int, round_type: str,
               input_paper_ids: list[str], output: dict, status: str = "done") -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO research_rounds "
            "(session_id, round_number, round_type, input_paper_ids, output_json, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, round_number, round_type,
             json.dumps(input_paper_ids, ensure_ascii=False),
             json.dumps(output, ensure_ascii=False),
             status, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def get_session(user_id: int, session_id: int) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM research_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["paper_ids"] = json.loads(result.pop("paper_ids_json", "[]"))
        result["config"] = json.loads(result.pop("config_json", "{}"))
        rounds = conn.execute(
            "SELECT * FROM research_rounds WHERE session_id = ? ORDER BY round_number",
            (session_id,),
        ).fetchall()
        result["rounds"] = []
        for r in rounds:
            rd = dict(r)
            rd["input_paper_ids"] = json.loads(rd.pop("input_paper_ids", "[]"))
            rd["output"] = json.loads(rd.pop("output_json", "{}"))
            result["rounds"].append(rd)
        return result
    finally:
        conn.close()


def list_sessions(
    user_id: int,
    limit: int = 20,
    saved_only: bool = False,
    retention_days: int | None = None,
) -> list[dict]:
    """
    List research sessions for a user.

    retention_days: if given, non-saved sessions older than this many days are excluded.
                    Saved sessions (saved=1) are always returned regardless of age.
                    None means no time-based filtering.
    """
    conn = _connect()
    try:
        where = "WHERE user_id = ?"
        params: list = [user_id]
        if saved_only:
            where += " AND saved = 1"
        elif retention_days is not None:
            # Keep saved sessions always; filter out unsaved ones beyond retention window
            cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
            where += " AND (saved = 1 OR created_at >= ?)"
            params.append(cutoff)
        params.append(limit)
        rows = conn.execute(
            f"SELECT id, question, status, created_at, updated_at, paper_ids_json, saved "
            f"FROM research_sessions {where} "
            f"ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        results = []
        for row in rows:
            r = dict(row)
            r["paper_ids"] = json.loads(r.pop("paper_ids_json", "[]"))
            r["saved"] = bool(r.get("saved", 0))
            results.append(r)
        return results
    finally:
        conn.close()


def delete_session(user_id: int, session_id: int) -> bool:
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM research_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def save_session(user_id: int, session_id: int, saved: bool = True) -> bool:
    """Mark or unmark a research session as saved/starred by the user."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE research_sessions SET saved = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (1 if saved else 0, _now_iso(), session_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def rename_session(user_id: int, session_id: int, new_question: str) -> bool:
    """Rename (update the question field of) a research session."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE research_sessions SET question = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (new_question.strip(), _now_iso(), session_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Folder-based tree (for "深度研究" sidebar)
# ---------------------------------------------------------------------------

_RESEARCH_FOLDER_SCOPE = "research"


def get_tree(user_id: int, retention_days: int | None = None) -> dict:
    """
    Return the full research session tree for a user:
    {
      "folders": [ ... nested folders, each with "children" and "sessions" ... ],
      "sessions": [ ... root-level sessions (folder_id == null) ... ]
    }
    Folders are stored in kb_folders (scope='research') in paper_analysis.db.
    Sessions come from research_sessions.

    retention_days: if given, non-saved sessions older than this many days are excluded.
                    Saved sessions (saved=1) are always included regardless of age.
    """
    conn = _connect()
    try:
        folder_rows = conn.execute(
            "SELECT * FROM kb_folders WHERE user_id = ? AND scope = ? ORDER BY created_at",
            (user_id, _RESEARCH_FOLDER_SCOPE),
        ).fetchall()

        if retention_days is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
            session_rows = conn.execute(
                "SELECT id, question, status, created_at, updated_at, paper_ids_json, saved, folder_id "
                "FROM research_sessions WHERE user_id = ? AND (saved = 1 OR created_at >= ?) "
                "ORDER BY created_at DESC",
                (user_id, cutoff),
            ).fetchall()
        else:
            session_rows = conn.execute(
                "SELECT id, question, status, created_at, updated_at, paper_ids_json, saved, folder_id "
                "FROM research_sessions WHERE user_id = ? "
                "ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
    finally:
        conn.close()

    # Build folder lookup
    folders_by_id: dict[int, dict] = {}
    for row in folder_rows:
        d = dict(row)
        d["children"] = []
        d["sessions"] = []
        folders_by_id[d["id"]] = d

    # Attach sessions to their folders (or collect root sessions)
    root_sessions: list[dict] = []
    for row in session_rows:
        s = dict(row)
        s["paper_ids"] = json.loads(s.pop("paper_ids_json", "[]"))
        s["saved"] = bool(s.get("saved", 0))
        fid = s.get("folder_id")
        if fid and fid in folders_by_id:
            folders_by_id[fid]["sessions"].append(s)
        else:
            root_sessions.append(s)

    # Build nested tree from flat folder list
    root_folders: list[dict] = []
    for folder in folders_by_id.values():
        pid = folder.get("parent_id")
        if pid and pid in folders_by_id:
            folders_by_id[pid]["children"].append(folder)
        else:
            root_folders.append(folder)

    return {"folders": root_folders, "sessions": root_sessions}


def move_sessions(user_id: int, session_ids: list[int], target_folder_id: int | None) -> int:
    """
    Batch-move research sessions to a target folder (None = root).
    Validates that the target folder belongs to the user and has scope='research'.
    Returns the number of updated rows.
    """
    if target_folder_id is not None:
        conn = _connect()
        try:
            owner = conn.execute(
                "SELECT user_id, scope FROM kb_folders WHERE id = ?",
                (target_folder_id,),
            ).fetchone()
            if owner is None or owner["user_id"] != user_id or owner["scope"] != _RESEARCH_FOLDER_SCOPE:
                target_folder_id = None
        finally:
            conn.close()

    if not session_ids:
        return 0

    conn = _connect()
    try:
        placeholders = ",".join("?" * len(session_ids))
        cur = conn.execute(
            f"UPDATE research_sessions SET folder_id = ?, updated_at = ? "
            f"WHERE id IN ({placeholders}) AND user_id = ?",
            [target_folder_id, _now_iso()] + list(session_ids) + [user_id],
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def _cleanup_stale_sessions(user_id: int) -> None:
    """Mark running sessions older than 10 minutes as error so the user is not permanently blocked."""
    conn = _connect()
    try:
        conn.execute(
            "UPDATE research_sessions SET status = 'error', updated_at = ? "
            "WHERE user_id = ? AND status = 'running' "
            "AND updated_at < datetime('now', '-10 minutes')",
            (_now_iso(), user_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_running_session_id(user_id: int) -> Optional[int]:
    """Return the ID of any running session for this user, or None."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id FROM research_sessions WHERE user_id = ? AND status = 'running' LIMIT 1",
            (user_id,),
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def has_running_session(user_id: int) -> bool:
    return get_running_session_id(user_id) is not None


def cancel_session(user_id: int, session_id: int) -> bool:
    """Cancel a running session so the user can start a new one."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE research_sessions SET status = 'error', updated_at = ? "
            "WHERE id = ? AND user_id = ? AND status = 'running'",
            (_now_iso(), session_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# File helpers — thin aliases to the shared paper_data_utils module
# ---------------------------------------------------------------------------

def _find_paper_dir(paper_id: str) -> Optional[str]:
    return _pdu.find_paper_dir(paper_id)


def _load_summary(paper_id: str) -> Optional[str]:
    return _pdu.load_summary(paper_id)


def _load_mineru(paper_id: str) -> Optional[str]:
    return _pdu.load_mineru(paper_id)


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _sse_text(round_num: int, content: str) -> str:
    return _sse({"type": "text", "round": round_num, "content": content})


def _sse_error(msg: str) -> Generator[str, None, None]:
    yield _sse({"type": "error", "content": msg})
    yield "data: [DONE]\n\n"


def _friendly_llm_error(exc: Exception) -> str:
    """将 LLM 客户端异常转换为对用户可操作的中文提示。"""
    if isinstance(exc, APIConnectionError):
        return (
            "无法连接到 LLM 服务（Connection error）。"
            "请检查：① 「个人中心 → AI 问答」中配置的 API 地址是否正确且可访问；"
            "② 网络或代理设置是否正常。"
        )
    if isinstance(exc, AuthenticationError):
        return (
            "LLM 认证失败（Authentication error）。"
            "请检查「个人中心 → AI 问答」中配置的 API Key 是否有效。"
        )
    if isinstance(exc, RateLimitError):
        return "LLM 请求频率超限（Rate limit）。请稍后重试，或检查账户配额。"
    if isinstance(exc, APIStatusError):
        return f"LLM 服务返回错误（HTTP {exc.status_code}）：{exc.message}"
    return str(exc)


def _run_round1_with_heartbeat(
    client: OpenAI,
    cfg: dict,
    question: str,
    papers: list[dict],
    session_id: int,
    result: list,
    cancel_event=None,
) -> Generator[str, None, None]:
    """
    Run Round 1 (synchronous LLM call) while emitting SSE heartbeat progress
    events every 4 seconds so the frontend never stalls on a blank spinner.

    Yields SSE ``progress`` events until the LLM call completes.
    The final result (rankings list or Exception) is written into *result[0]*.
    """
    import queue as _queue
    q: _queue.Queue = _queue.Queue()

    def _worker():
        try:
            rankings = _run_round1(client, cfg, question, papers)
            q.put(("ok", rankings))
        except Exception as exc:
            q.put(("error", exc))

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    elapsed = 0
    while True:
        try:
            tag, val = q.get(timeout=4)
            result.append(val)  # store rankings or Exception
            return
        except _queue.Empty:
            if cancel_event is not None and cancel_event.is_set():
                result.append(RuntimeError("cancelled"))
                return
            elapsed += 4
            _touch_session(session_id)
            yield _sse({
                "type": "progress", "round": 1,
                "message": f"正在评估 {len(papers)} 篇论文的相关性…（已等待 {elapsed}s）",
            })


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _get_llm_config(user_id: int) -> dict:
    """
    Load LLM config for deep research.

    Priority:
      1. ``deep_research`` feature settings (if llm_model is configured)
      2. ``paper_chat`` feature settings as fallback (preserves backward compat)
    """
    us = _get_user_settings_service()
    ups = _get_user_presets_service()

    cfg = us.get_settings(user_id, "deep_research")

    # Fall back to paper_chat if deep_research has no model configured
    if not (cfg.get("llm_preset_id") or (cfg.get("llm_model") or "").strip()):
        fallback = us.get_settings(user_id, "paper_chat")
        # Merge: take connection params from fallback but keep deep_research defaults for limits
        for key in ("llm_base_url", "llm_api_key", "llm_model", "llm_preset_id"):
            if fallback.get(key):
                cfg[key] = fallback[key]

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
    return cfg


def _make_client(cfg: dict) -> Optional[OpenAI]:
    url = (cfg.get("llm_base_url") or "").strip()
    key = (cfg.get("llm_api_key") or "").strip()
    if not url or not key:
        return None
    return OpenAI(api_key=key, base_url=url)


def _call_llm_sync(client: OpenAI, cfg: dict, messages: list[dict],
                   max_tokens_override: Optional[int] = None) -> str:
    """Non-streaming LLM call; returns the reply text."""
    kwargs: dict = {}
    temperature = cfg.get("temperature")
    if temperature is not None:
        kwargs["temperature"] = float(temperature)
    mt = max_tokens_override or cfg.get("max_tokens")
    if mt is not None:
        kwargs["max_tokens"] = int(mt)

    resp = client.chat.completions.create(
        model=(cfg.get("llm_model") or "").strip(),
        messages=messages,
        stream=False,
        **kwargs,
    )
    return resp.choices[0].message.content or ""


def _stream_llm(client: OpenAI, cfg: dict, messages: list[dict],
                round_num: int,
                error_state: Optional[list] = None,
                cancel_event=None) -> Generator[str, None, None]:
    """Streaming LLM call; yields SSE text events for the given round.

    If an API error occurs, an error SSE event is yielded and error_state[0] is
    set to the exception so the caller can detect failure after exhausting the
    generator.  If cancel_event is set mid-stream the generator exits early.
    """
    kwargs: dict = {}
    temperature = cfg.get("temperature")
    if temperature is not None:
        kwargs["temperature"] = float(temperature)
    mt = cfg.get("max_tokens")
    if mt is not None:
        kwargs["max_tokens"] = int(mt)

    try:
        response = client.chat.completions.create(
            model=(cfg.get("llm_model") or "").strip(),
            messages=messages,
            stream=True,
            **kwargs,
        )
        for chunk in response:
            if cancel_event is not None and cancel_event.is_set():
                break
            if chunk.choices and chunk.choices[0].delta.content:
                yield _sse_text(round_num, chunk.choices[0].delta.content)
    except Exception as exc:
        yield _sse({"type": "error", "round": round_num, "content": f"LLM 调用失败: {_friendly_llm_error(exc)}"})
        if error_state is not None:
            error_state.append(exc)


# ---------------------------------------------------------------------------
# Round 1 — Relevance ranking
# ---------------------------------------------------------------------------

_ROUND1_SYSTEM = """你是一个学术论文相关性评估专家。
给定一个研究问题和若干论文的摘要/标题，请评估每篇论文与该问题的相关性，并输出 JSON 排序结果。

输出格式（严格 JSON，不要有任何多余文字）：
{
  "rankings": [
    {
      "paper_id": "论文ID",
      "score": 0.95,
      "level": "high",
      "reason": "相关性原因（一句话）"
    }
  ]
}

score 范围 0.0-1.0，level 为 "high"(>=0.6)、"medium"(>=0.3)、"low"(<0.3)。
按 score 从高到低排序。所有输入论文都必须出现在输出中。"""


def _run_round1(client: OpenAI, cfg: dict, question: str,
                papers: list[dict]) -> list[dict]:
    """
    Call LLM to rank papers by relevance.
    Returns a list of ranking dicts sorted by score descending.
    """
    parts = [f"研究问题：{question}\n\n论文列表："]
    for p in papers:
        pd = p.get("paper_data", {})
        pid = p.get("paper_id", "")
        title = pd.get("📖标题") or pd.get("short_title") or pid
        abstract = pd.get("abstract", "")
        intro = pd.get("🛎️文章简介", {})
        if isinstance(intro, dict):
            research_q = intro.get("🔸研究问题", "")
            contribution = intro.get("🔸主要贡献", "")
        else:
            research_q = contribution = ""
        parts.append(
            f"\n--- 论文 ID: {pid} ---\n"
            f"标题: {title}\n"
            f"摘要: {abstract[:400] if abstract else '（无）'}\n"
            f"研究问题: {research_q[:200] if research_q else '（无）'}\n"
            f"主要贡献: {contribution[:200] if contribution else '（无）'}"
        )

    user_content = "\n".join(parts)
    hard_limit = int(cfg.get("input_hard_limit", 129024))
    safety_margin = int(cfg.get("input_safety_margin", 4096))
    budget = hard_limit - safety_margin - _approx_tokens(_ROUND1_SYSTEM)
    user_content = _crop(user_content, budget)

    reply = _call_llm_sync(client, cfg, [
        {"role": "system", "content": _ROUND1_SYSTEM},
        {"role": "user", "content": user_content},
    ], max_tokens_override=2048)

    # Extract JSON from reply (may be wrapped in markdown fences)
    text = reply.strip()
    if "```" in text:
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
    # Find the outermost {...}
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]

    try:
        data = json.loads(text)
        rankings = data.get("rankings", [])
        if not rankings:
            raise ValueError("empty rankings")
        return rankings
    except Exception:
        # Fallback: return papers in original order with equal scores
        return [
            {"paper_id": p.get("paper_id", ""), "score": 0.5,
             "level": "medium", "reason": "无法解析 LLM 排序结果，保留原始顺序"}
            for p in papers
        ]


# ---------------------------------------------------------------------------
# Round 2 — Summary analysis
# ---------------------------------------------------------------------------

_ROUND2_SYSTEM = """你是一个学术研究助手，擅长从论文摘要中提炼信息并回答研究问题。

你的任务：
1. 仔细阅读给定论文的 AI 摘要，尝试回答用户的研究问题。
2. 如果摘要中的信息足够回答问题，请直接给出详尽、有条理的回答。
3. 如果摘要信息不足（需要查阅全文的实验数据、详细方法或具体数值），请在回答末尾附上以下 JSON 块（不要在其他地方输出 JSON）：

```json
{"action":"read_full","papers":["paper_id_1","paper_id_2"]}
```

只有当确实需要全文才能更好回答时才建议阅读全文。如果摘要已足够，不要输出 JSON 块。
回答时请用中文，结构清晰，引用具体论文时注明论文 ID。"""


def _run_round2(client: OpenAI, cfg: dict, question: str, papers: list[dict],
                selected_ids: list[str], paper_titles: dict[str, str],
                context: Optional[str] = None,
                error_state: Optional[list] = None,
                cancel_event=None) -> Generator[str, None, None]:
    """Stream Round 2 and yield SSE events. Also returns final text and action via state dict."""
    intro = f"研究问题：{question}"
    if context:
        intro += f"\n\n[追问背景 - 上轮研究结论]\n{context}"
    intro += "\n\n以下是相关论文的 AI 摘要："
    parts = [intro]
    for pid in selected_ids:
        title = paper_titles.get(pid, pid)
        summary = _load_summary(pid)
        if not summary:
            # Fallback to paper_data fields
            paper_data = next((p.get("paper_data", {}) for p in papers if p.get("paper_id") == pid), {})
            intro = paper_data.get("🛎️文章简介", {})
            if isinstance(intro, dict):
                summary = (
                    f"研究问题：{intro.get('🔸研究问题', '未知')}\n"
                    f"主要贡献：{intro.get('🔸主要贡献', '未知')}"
                )
            else:
                summary = paper_data.get("abstract", "（无摘要数据）")
        parts.append(f"\n--- 论文 {pid}（{title}）---\n{summary}")

    user_content = "\n".join(parts)
    hard_limit = int(cfg.get("input_hard_limit", 129024))
    safety_margin = int(cfg.get("input_safety_margin", 4096))
    budget = hard_limit - safety_margin - _approx_tokens(_ROUND2_SYSTEM)
    user_content = _crop(user_content, budget)

    yield from _stream_llm(client, cfg, [
        {"role": "system", "content": _ROUND2_SYSTEM},
        {"role": "user", "content": user_content},
    ], round_num=2, error_state=error_state, cancel_event=cancel_event)


def _parse_round2_action(full_text: str) -> tuple[str, list[str], str]:
    """
    Parse the Round 2 full reply text.
    Returns (action, paper_ids, decision_reason):
      action = "answer" or "read_full"
      paper_ids = list of paper_ids to read (empty if action=="answer")
      decision_reason = human-readable explanation of the decision

    Tries two patterns in order:
      1. JSON wrapped in a code fence (preferred, as instructed in the prompt)
      2. Bare JSON object without a code fence (fallback for non-conforming LLM output)
    """
    import re

    def _try_parse(candidate: str) -> tuple[str, list[str]] | None:
        try:
            data = json.loads(candidate)
            if data.get("action") == "read_full":
                papers = data.get("papers", [])
                if isinstance(papers, list) and papers:
                    return "read_full", papers
        except Exception:
            pass
        return None

    # Pattern 1: JSON inside a code fence
    m = re.search(
        r'```(?:json)?\s*(\{[^`]*?"action"\s*:\s*"read_full"[^`]*?\})\s*```',
        full_text, re.DOTALL,
    )
    if m:
        result = _try_parse(m.group(1))
        if result:
            return result[0], result[1], "AI 分析认为摘要信息不足，需要阅读论文全文才能完整回答"

    # Pattern 2: bare JSON object (no code fence)
    m = re.search(
        r'(\{[^{}]*?"action"\s*:\s*"read_full"[^{}]*?\})',
        full_text, re.DOTALL,
    )
    if m:
        result = _try_parse(m.group(1))
        if result:
            return result[0], result[1], "AI 分析认为摘要信息不足，需要阅读论文全文才能完整回答"

    return "answer", [], "AI 摘要分析已足以直接回答该问题"


# ---------------------------------------------------------------------------
# Round 3 — Full-text deep read
# ---------------------------------------------------------------------------

_ROUND3_SYSTEM = """你是一个学术研究助手，能够深度分析论文全文并回答研究问题。

你已经阅读了相关论文的摘要并做了初步分析，现在你获得了以下论文的全文内容（经过结构化解析）。
请结合全文内容，给出更深入、更准确的回答。

回答要求：
- 用中文，条理清晰
- 引用具体证据时注明来源论文 ID 和相关章节
- 如果全文中有关键实验数据、方法细节或结论，要明确引用
- 综合之前的摘要分析和本次全文阅读，给出完整的最终回答"""


def _run_round3(client: OpenAI, cfg: dict, question: str, summary_analysis: str,
                papers_to_read: list[str], rankings: list[dict],
                paper_titles: dict[str, str],
                error_state: Optional[list] = None,
                cancel_event=None) -> Generator[str, None, None]:
    """Stream Round 3 full-text analysis and yield SSE events."""
    hard_limit = int(cfg.get("input_hard_limit", 129024))
    safety_margin = int(cfg.get("input_safety_margin", 4096))
    system_tokens = _approx_tokens(_ROUND3_SYSTEM)
    question_tokens = _approx_tokens(question)
    summary_tokens = _approx_tokens(summary_analysis)
    available_for_fulltext = hard_limit - safety_margin - system_tokens - question_tokens - summary_tokens - 2000

    # Sort papers_to_read by their Round 1 relevance score
    score_map = {r["paper_id"]: r.get("score", 0) for r in rankings}
    sorted_papers = sorted(papers_to_read, key=lambda pid: score_map.get(pid, 0), reverse=True)

    parts = [
        f"研究问题：{question}",
        f"\n[摘要分析结果]\n{summary_analysis}",
        "\n\n[以下是论文全文内容]",
    ]
    remaining_budget = available_for_fulltext
    truncated_papers: list[str] = []
    skipped_papers: list[str] = []

    for pid in sorted_papers:
        if remaining_budget <= 0:
            skipped_papers.append(pid)
            continue
        title = paper_titles.get(pid, pid)
        content = _load_mineru(pid)
        if not content:
            content = _load_summary(pid) or "（全文不可用，仅有摘要）"
        tokens_needed = _approx_tokens(content)
        if tokens_needed > remaining_budget:
            content = _crop(content, remaining_budget)
            tokens_needed = remaining_budget
            truncated_papers.append(pid)
        parts.append(f"\n--- 论文 {pid}（{title}）全文 ---\n{content}")
        remaining_budget -= tokens_needed

    # Notify frontend of any truncation or skipping due to token budget
    if truncated_papers or skipped_papers:
        msgs = []
        if truncated_papers:
            names = "、".join(paper_titles.get(p, p) for p in truncated_papers)
            msgs.append(f"以下论文因内容过长已截取部分：{names}")
        if skipped_papers:
            names = "、".join(paper_titles.get(p, p) for p in skipped_papers)
            msgs.append(f"以下论文因 token 预算已满被跳过：{names}")
        yield _sse({"type": "progress", "round": 3, "message": "⚠️ " + "；".join(msgs)})

    user_content = "\n".join(parts)

    yield from _stream_llm(client, cfg, [
        {"role": "system", "content": _ROUND3_SYSTEM},
        {"role": "user", "content": user_content},
    ], round_num=3, error_state=error_state, cancel_event=cancel_event)


# ---------------------------------------------------------------------------
# Main streaming generator
# ---------------------------------------------------------------------------

def stream_research(
    user_id: int,
    question: str,
    paper_ids: list[str],
    scope: str = "kb",
    config: Optional[dict] = None,
    cancel_event=None,
) -> Generator[str, None, None]:
    """
    Generator that yields SSE-formatted strings for the full research workflow.

    Emits structured JSON events (see module docstring) plus a terminal
        data: [DONE]
    """
    if config is None:
        config = {}

    top_n: int = max(1, min(int(config.get("top_n", 5)), len(paper_ids)))
    force_full_read: bool = bool(config.get("force_full_read", False))

    # Clean up stale running sessions before checking (self-healing guard)
    _cleanup_stale_sessions(user_id)

    # Guard: one running session per user
    running_id = get_running_session_id(user_id)
    if running_id is not None:
        yield _sse({"type": "error", "content": "当前有进行中的研究会话，请等待其完成后再开始新的研究。",
                    "running_session_id": running_id})
        yield "data: [DONE]\n\n"
        return

    # Load LLM config
    cfg = _get_llm_config(user_id)
    llm_url = (cfg.get("llm_base_url") or "").strip()
    llm_key = (cfg.get("llm_api_key") or "").strip()
    llm_model = (cfg.get("llm_model") or "").strip()

    if not llm_url or not llm_key or not llm_model:
        yield from _sse_error(
            "请先在「个人中心 → AI 问答」中配置 LLM 的 URL、API Key 和 Model，或选择一个模型预设。"
        )
        return

    client = _make_client(cfg)
    if not client:
        yield from _sse_error("LLM 客户端初始化失败，请检查配置。")
        return

    # Create session — persist scope inside config so it is available when replaying history
    session_config = dict(config)
    session_config["scope"] = scope
    session_id: Optional[int] = None  # initialise before try so outer except can reference it safely
    session_id = create_session(user_id, question, paper_ids, session_config)

    # Emit session_id immediately so the frontend can use it for follow-up requests.
    yield _sse({"type": "session_created", "session_id": session_id})

    try:
        # ------------------------------------------------------------------
        # Round 1: Relevance ranking
        # ------------------------------------------------------------------
        yield _sse({
            "type": "round_start",
            "round": 1,
            "title": "分析问题与论文相关性",
            "total_papers": len(paper_ids),
        })

        cs = _get_compare_service()
        papers = cs.get_papers_by_ids(user_id, paper_ids, scope)

        # Build title map
        paper_titles: dict[str, str] = {}
        for p in papers:
            pd = p.get("paper_data", {})
            pid = p.get("paper_id", "")
            paper_titles[pid] = pd.get("📖标题") or pd.get("short_title") or pid

        yield _sse({"type": "progress", "round": 1, "message": f"正在评估 {len(papers)} 篇论文的相关性…"})

        round1_result: list = []
        try:
            yield from _run_round1_with_heartbeat(
                client, cfg, question, papers, session_id, round1_result, cancel_event,
            )
        except Exception as exc:
            yield _sse({"type": "error", "round": 1, "content": f"相关性排序失败: {_friendly_llm_error(exc)}"})
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        if not round1_result:
            yield _sse({"type": "error", "round": 1, "content": "相关性排序未返回结果。"})
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        rankings_or_exc = round1_result[0]
        if isinstance(rankings_or_exc, Exception):
            yield _sse({"type": "error", "round": 1, "content": f"相关性排序失败: {_friendly_llm_error(rankings_or_exc)}"})
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        rankings = rankings_or_exc

        # Sort by score descending (don't rely on LLM-returned order) then take top N
        ranked_sorted = sorted(rankings, key=lambda r: r.get("score", 0), reverse=True)
        top_papers = ranked_sorted[:top_n]
        selected_ids = [r["paper_id"] for r in top_papers]

        yield _sse({
            "type": "relevance_result",
            "round": 1,
            "rankings": ranked_sorted,  # score-sorted so frontend groups are in score order
            "selected_ids": selected_ids,
            "top_n": top_n,
            "paper_titles": paper_titles,
        })

        save_round(session_id, 1, "relevance",
                   paper_ids,
                   {"rankings": ranked_sorted, "selected_ids": selected_ids, "top_n": top_n})
        _touch_session(session_id)

        if not selected_ids:
            yield _sse({"type": "error", "round": 1, "content": "未能从所选论文中筛选出相关论文。"})
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        yield _sse({"type": "round_done", "round": 1})

        # Check for client cancellation before starting the next round.
        if cancel_event is not None and cancel_event.is_set():
            update_session_status(session_id, "error")
            return

        # ------------------------------------------------------------------
        # Round 2: Summary analysis
        # ------------------------------------------------------------------
        yield _sse({
            "type": "round_start",
            "round": 2,
            "title": "基于 AI 摘要分析",
            "selected_papers": len(selected_ids),
            "paper_titles": {pid: paper_titles.get(pid, pid) for pid in selected_ids},
        })

        full_round2_text = ""
        round2_error: list = []
        try:
            for chunk in _run_round2(client, cfg, question, papers, selected_ids, paper_titles,
                                     error_state=round2_error, cancel_event=cancel_event):
                if chunk.startswith("data: "):
                    # Capture text chunks for later parsing
                    raw = chunk[6:].strip()
                    if raw and raw != "[DONE]":
                        try:
                            evt = json.loads(raw)
                            if evt.get("type") == "text":
                                full_round2_text += evt.get("content", "")
                        except Exception:
                            pass
                yield chunk
        except Exception as exc:
            yield _sse({"type": "error", "round": 2, "content": f"摘要分析失败: {exc}"})
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        if round2_error:
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        # Parse Round 2 output to decide next action
        action, papers_to_read, decision_reason = _parse_round2_action(full_round2_text)
        # Validate paper IDs are in selected set
        papers_to_read = [pid for pid in papers_to_read if pid in selected_ids]

        yield _sse({
            "type": "round_done",
            "round": 2,
            "action": action,
            "papers": papers_to_read,
            "decision_reason": decision_reason,
        })

        save_round(session_id, 2, "summary_analysis",
                   selected_ids,
                   {"action": action, "papers_to_read": papers_to_read,
                    "full_text": full_round2_text})
        _touch_session(session_id)

        if (action == "answer" or not papers_to_read) and not force_full_read:
            yield _sse({"type": "final_answer"})
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "done")
            return

        # force_full_read: if LLM answered without requesting full text,
        # use all selected papers for Round 3.
        if force_full_read and not papers_to_read:
            papers_to_read = selected_ids

        # Check for client cancellation before starting the next round.
        if cancel_event is not None and cancel_event.is_set():
            update_session_status(session_id, "error")
            return

        # ------------------------------------------------------------------
        # Round 3: Full-text deep read
        # ------------------------------------------------------------------
        yield _sse({
            "type": "round_start",
            "round": 3,
            "title": "深度阅读全文",
            "papers_count": len(papers_to_read),
            "paper_titles": {pid: paper_titles.get(pid, pid) for pid in papers_to_read},
        })

        full_round3_text = ""
        round3_error: list = []
        try:
            for chunk in _run_round3(client, cfg, question, full_round2_text,
                                     papers_to_read, rankings, paper_titles,
                                     error_state=round3_error, cancel_event=cancel_event):
                if chunk.startswith("data: "):
                    raw = chunk[6:].strip()
                    if raw and raw != "[DONE]":
                        try:
                            evt = json.loads(raw)
                            if evt.get("type") == "text":
                                full_round3_text += evt.get("content", "")
                        except Exception:
                            pass
                yield chunk
        except Exception as exc:
            yield _sse({"type": "error", "round": 3, "content": f"全文分析失败: {exc}"})
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        if round3_error:
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        save_round(session_id, 3, "full_text",
                   papers_to_read,
                   {"full_text": full_round3_text})
        _touch_session(session_id)

        yield _sse({"type": "final_answer"})
        yield "data: [DONE]\n\n"
        update_session_status(session_id, "done")

    except Exception as exc:
        yield _sse({"type": "error", "content": f"研究会话异常: {exc}"})
        yield "data: [DONE]\n\n"
        if session_id is not None:
            try:
                update_session_status(session_id, "error")
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Continue Round 3 from an existing completed session
# ---------------------------------------------------------------------------

def stream_continue_round3(
    user_id: int,
    session_id: int,
    cancel_event=None,
) -> Generator[str, None, None]:
    """
    Resume a *done* research session by running Round 3 (full-text deep read)
    using the Round 1 rankings and Round 2 output that were already saved.

    This avoids repeating the expensive Round 1 + Round 2 LLM calls when the
    user clicks "深度阅读全文" after a summary-only answer.

    Emits the same SSE events as ``stream_research`` for round 3.
    """
    # Load the session
    session = get_session(user_id, session_id)
    if session is None:
        yield from _sse_error("研究会话不存在或无权访问。")
        return

    if session["status"] not in ("done", "error"):
        yield from _sse_error("该会话尚未完成，无法续接 Round 3。")
        return

    rounds = session.get("rounds", [])
    r1 = next((r for r in rounds if r["round_type"] == "relevance"), None)
    r2 = next((r for r in rounds if r["round_type"] == "summary_analysis"), None)

    if r1 is None or r2 is None:
        yield from _sse_error("缺少 Round 1 或 Round 2 数据，无法续接 Round 3。")
        return

    # Check Round 2 action — only proceed if it already answered (not read_full)
    # or if there are selected papers we can read.
    r2_output = r2.get("output", {})
    r1_output = r1.get("output", {})
    rankings = r1_output.get("rankings", [])
    selected_ids: list[str] = r1_output.get("selected_ids", [])

    # If R2 already said read_full, respect its paper list; otherwise use all selected.
    if r2_output.get("action") == "read_full" and r2_output.get("papers_to_read"):
        papers_to_read: list[str] = r2_output["papers_to_read"]
    else:
        papers_to_read = selected_ids

    if not papers_to_read:
        yield from _sse_error("没有可供深读的论文 ID。")
        return

    # Load LLM config
    cfg = _get_llm_config(user_id)
    client = _make_client(cfg)
    if not client:
        yield from _sse_error("LLM 客户端初始化失败，请检查配置。")
        return

    # Build title map from paper_ids in session
    cs = _get_compare_service()
    papers = cs.get_papers_by_ids(user_id, session["paper_ids"], session.get("config", {}).get("scope", "kb"))
    paper_titles: dict[str, str] = {}
    for p in papers:
        pd = p.get("paper_data", {})
        pid = p.get("paper_id", "")
        paper_titles[pid] = pd.get("📖标题") or pd.get("short_title") or pid

    summary_analysis_text: str = r2_output.get("full_text", "")

    # Mark session running again
    update_session_status(session_id, "running")

    try:
        yield _sse({
            "type": "round_start",
            "round": 3,
            "title": "深度阅读全文",
            "papers_count": len(papers_to_read),
            "paper_titles": {pid: paper_titles.get(pid, pid) for pid in papers_to_read},
        })

        full_round3_text = ""
        round3_error: list = []
        try:
            for chunk in _run_round3(client, cfg, session["question"], summary_analysis_text,
                                     papers_to_read, rankings, paper_titles,
                                     error_state=round3_error, cancel_event=cancel_event):
                if chunk.startswith("data: "):
                    raw = chunk[6:].strip()
                    if raw and raw != "[DONE]":
                        try:
                            evt = json.loads(raw)
                            if evt.get("type") == "text":
                                full_round3_text += evt.get("content", "")
                        except Exception:
                            pass
                yield chunk
        except Exception as exc:
            yield _sse({"type": "error", "round": 3, "content": f"全文分析失败: {exc}"})
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        if round3_error:
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        save_round(session_id, 3, "full_text",
                   papers_to_read,
                   {"full_text": full_round3_text})
        _touch_session(session_id)

        yield _sse({"type": "final_answer"})
        yield "data: [DONE]\n\n"
        update_session_status(session_id, "done")

    except Exception as exc:
        yield _sse({"type": "error", "content": f"续接 Round 3 异常: {exc}"})
        yield "data: [DONE]\n\n"
        try:
            update_session_status(session_id, "error")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Follow-up: reuse R1 from parent session, only re-run R2 + R3
# ---------------------------------------------------------------------------

def stream_followup(
    user_id: int,
    parent_session_id: int,
    question: str,
    context: Optional[str] = None,
    cancel_event=None,
) -> Generator[str, None, None]:
    """
    Start a follow-up research session by reusing Round 1 from an existing completed session.

    Loads the R1 rankings and selected paper IDs from *parent_session_id*, then runs
    Round 2 (and optionally Round 3) with the new *question*.  The optional *context*
    string (e.g. the previous answer) is injected into the Round 2 prompt so the LLM
    has continuity without the caller having to embed it in the question text.

    A new child session is created with ``parent_session_id`` set; R1 is saved as
    a "relevance_reuse" round so the history viewer can distinguish it.
    """
    # Load parent session
    parent = get_session(user_id, parent_session_id)
    if parent is None:
        yield from _sse_error("父会话不存在或无权访问。")
        return

    if parent["status"] not in ("done", "error"):
        yield from _sse_error("父会话尚未完成，无法追问。")
        return

    rounds = parent.get("rounds", [])
    r1 = next((r for r in rounds if r["round_type"] in ("relevance", "relevance_reuse")), None)
    if r1 is None:
        yield from _sse_error("父会话缺少相关性排序数据，无法追问。")
        return

    r1_output = r1.get("output", {})
    rankings = r1_output.get("rankings", [])
    selected_ids: list[str] = r1_output.get("selected_ids", [])

    if not selected_ids:
        yield from _sse_error("父会话未选中任何相关论文，无法追问。")
        return

    # Cleanup stale sessions and guard concurrency
    _cleanup_stale_sessions(user_id)
    running_id = get_running_session_id(user_id)
    if running_id is not None:
        yield _sse({"type": "error", "content": "当前有进行中的研究会话，请等待其完成后再开始新的研究。",
                    "running_session_id": running_id})
        yield "data: [DONE]\n\n"
        return

    # Load LLM config
    cfg = _get_llm_config(user_id)
    llm_url = (cfg.get("llm_base_url") or "").strip()
    llm_key = (cfg.get("llm_api_key") or "").strip()
    llm_model = (cfg.get("llm_model") or "").strip()

    if not llm_url or not llm_key or not llm_model:
        yield from _sse_error(
            "请先在「个人中心 → AI 问答」中配置 LLM 的 URL、API Key 和 Model，或选择一个模型预设。"
        )
        return

    client = _make_client(cfg)
    if not client:
        yield from _sse_error("LLM 客户端初始化失败，请检查配置。")
        return

    # Load paper data for title map and R2 prompting
    scope = parent.get("config", {}).get("scope", "kb")
    cs = _get_compare_service()
    papers = cs.get_papers_by_ids(user_id, parent["paper_ids"], scope)
    paper_titles: dict[str, str] = {}
    for p in papers:
        pd = p.get("paper_data", {})
        pid = p.get("paper_id", "")
        paper_titles[pid] = pd.get("📖标题") or pd.get("short_title") or pid

    # Create child session (reuses parent's paper_ids and config)
    child_config = dict(parent.get("config", {}))
    session_id: Optional[int] = None
    session_id = create_session(
        user_id, question, parent["paper_ids"], child_config,
        parent_session_id=parent_session_id,
    )

    yield _sse({"type": "session_created", "session_id": session_id})

    try:
        # ------------------------------------------------------------------
        # Round 1: Replay parent's R1 results — no new LLM call
        # ------------------------------------------------------------------
        yield _sse({
            "type": "round_start",
            "round": 1,
            "title": "复用相关性分析（追问）",
            "total_papers": len(parent["paper_ids"]),
        })
        yield _sse({
            "type": "relevance_result",
            "round": 1,
            "rankings": rankings,
            "selected_ids": selected_ids,
            "top_n": len(selected_ids),
            "paper_titles": paper_titles,
        })
        save_round(session_id, 1, "relevance_reuse",
                   parent["paper_ids"],
                   {"rankings": rankings, "selected_ids": selected_ids,
                    "top_n": len(selected_ids), "reused_from": parent_session_id})
        yield _sse({"type": "round_done", "round": 1})

        if cancel_event is not None and cancel_event.is_set():
            update_session_status(session_id, "error")
            return

        # ------------------------------------------------------------------
        # Round 2: Summary analysis with new question (+ optional context)
        # ------------------------------------------------------------------
        yield _sse({
            "type": "round_start",
            "round": 2,
            "title": "基于 AI 摘要分析（追问）",
            "selected_papers": len(selected_ids),
            "paper_titles": {pid: paper_titles.get(pid, pid) for pid in selected_ids},
        })

        full_round2_text = ""
        round2_error: list = []
        try:
            for chunk in _run_round2(client, cfg, question, papers, selected_ids, paper_titles,
                                     context=context,
                                     error_state=round2_error, cancel_event=cancel_event):
                if chunk.startswith("data: "):
                    raw = chunk[6:].strip()
                    if raw and raw != "[DONE]":
                        try:
                            evt = json.loads(raw)
                            if evt.get("type") == "text":
                                full_round2_text += evt.get("content", "")
                        except Exception:
                            pass
                yield chunk
        except Exception as exc:
            yield _sse({"type": "error", "round": 2, "content": f"摘要分析失败: {exc}"})
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        if round2_error:
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        action, papers_to_read, decision_reason = _parse_round2_action(full_round2_text)
        papers_to_read = [pid for pid in papers_to_read if pid in selected_ids]

        yield _sse({
            "type": "round_done",
            "round": 2,
            "action": action,
            "papers": papers_to_read,
            "decision_reason": decision_reason,
        })

        save_round(session_id, 2, "summary_analysis",
                   selected_ids,
                   {"action": action, "papers_to_read": papers_to_read,
                    "full_text": full_round2_text})
        _touch_session(session_id)

        if action == "answer" or not papers_to_read:
            yield _sse({"type": "final_answer"})
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "done")
            return

        if cancel_event is not None and cancel_event.is_set():
            update_session_status(session_id, "error")
            return

        # ------------------------------------------------------------------
        # Round 3: Full-text deep read
        # ------------------------------------------------------------------
        yield _sse({
            "type": "round_start",
            "round": 3,
            "title": "深度阅读全文（追问）",
            "papers_count": len(papers_to_read),
            "paper_titles": {pid: paper_titles.get(pid, pid) for pid in papers_to_read},
        })

        full_round3_text = ""
        round3_error: list = []
        try:
            for chunk in _run_round3(client, cfg, question, full_round2_text,
                                     papers_to_read, rankings, paper_titles,
                                     error_state=round3_error, cancel_event=cancel_event):
                if chunk.startswith("data: "):
                    raw = chunk[6:].strip()
                    if raw and raw != "[DONE]":
                        try:
                            evt = json.loads(raw)
                            if evt.get("type") == "text":
                                full_round3_text += evt.get("content", "")
                        except Exception:
                            pass
                yield chunk
        except Exception as exc:
            yield _sse({"type": "error", "round": 3, "content": f"全文分析失败: {exc}"})
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        if round3_error:
            yield "data: [DONE]\n\n"
            update_session_status(session_id, "error")
            return

        save_round(session_id, 3, "full_text",
                   papers_to_read,
                   {"full_text": full_round3_text})
        _touch_session(session_id)

        yield _sse({"type": "final_answer"})
        yield "data: [DONE]\n\n"
        update_session_status(session_id, "done")

    except Exception as exc:
        yield _sse({"type": "error", "content": f"追问会话异常: {exc}"})
        yield "data: [DONE]\n\n"
        if session_id is not None:
            try:
                update_session_status(session_id, "error")
            except Exception:
                pass
