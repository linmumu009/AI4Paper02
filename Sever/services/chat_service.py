"""
Paper chat service.

Provides multi-turn conversational Q&A for a single paper.  Each user gets
one session per paper; messages are persisted in SQLite so that history
survives page reloads.

LLM connection parameters (url, key, model) are read from the per-user
settings stored in the ``user_settings`` table (feature = "paper_chat").
If the user has not configured them, the chat is unavailable.

Paper context (full text / summary / abstract) is injected into the system
prompt so the LLM can answer questions grounded in the paper content.

Context strategies
------------------
- ``recent_k`` (default): pass only the most recent K turns (2*K messages)
  to the LLM.  Cheap, predictable token cost.
- ``summary``: maintain a rolling summary of older messages.  When unsummarised
  history exceeds K turns, the oldest surplus messages are compressed by a
  synchronous LLM call (non-streaming, max_tokens=512) and the result is stored
  in ``paper_chat_sessions.context_summary``.  Each request then sends:
  ``[system+paper] + [summary_msg] + [recent 2K msgs]``.
- ``full``: send the complete history; drop oldest messages only when the
  token budget is exhausted.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Generator, Optional

from openai import OpenAI

# ---------------------------------------------------------------------------
# Lazy service imports (avoid circular imports)
# ---------------------------------------------------------------------------

_user_settings_service = None
_user_presets_service = None
_data_service = None
_user_paper_service = None


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


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")

# Reserved paper_id for site-wide general assistant (one session per user).
GENERAL_CHAT_PAPER_ID = "__ai4papers_general__"


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
    """Create chat tables if they do not exist, and run safe column migrations."""
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS paper_chat_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                paper_id    TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL,
                UNIQUE (user_id, paper_id)
            );

            CREATE TABLE IF NOT EXISTS paper_chat_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  INTEGER NOT NULL
                                REFERENCES paper_chat_sessions(id) ON DELETE CASCADE,
                role        TEXT    NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content     TEXT    NOT NULL,
                created_at  TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                ON paper_chat_messages(session_id, created_at);
            """
        )
        conn.commit()

        # Safe migrations: add columns if they don't already exist
        _safe_add_column(conn, "paper_chat_sessions", "context_summary",
                         "TEXT NOT NULL DEFAULT ''")
        _safe_add_column(conn, "paper_chat_sessions", "summary_up_to_msg_id",
                         "INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    finally:
        conn.close()


def _safe_add_column(conn: sqlite3.Connection, table: str, column: str, col_def: str) -> None:
    """Add a column to an existing table; silently ignore if it already exists."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
    except sqlite3.OperationalError:
        pass  # Column already exists


# ---------------------------------------------------------------------------
# File-collect helpers (mirror of compare_service pattern)
# ---------------------------------------------------------------------------

_FILE_COLLECT_DIR = os.path.join(_BASE_DIR, "data", "file_collect")


def _find_paper_dir(paper_id: str) -> Optional[str]:
    if ".." in paper_id or "/" in paper_id or "\\" in paper_id or "\x00" in paper_id:
        return None
    if not os.path.isdir(_FILE_COLLECT_DIR):
        return None
    for date_dir in sorted(os.listdir(_FILE_COLLECT_DIR), reverse=True):
        paper_dir = os.path.join(_FILE_COLLECT_DIR, date_dir, paper_id)
        if os.path.isdir(paper_dir):
            return paper_dir
    return None


def _read_file(path: str) -> Optional[str]:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _load_paper_content(paper_id: str, data_source: str) -> Optional[str]:
    """Load paper content from file_collect based on data_source setting."""
    paper_dir = _find_paper_dir(paper_id)
    if not paper_dir:
        return None

    if data_source == "full_text":
        return _read_file(os.path.join(paper_dir, f"{paper_id}_mineru.md"))
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
    else:  # "summary" (default)
        return _read_file(os.path.join(paper_dir, f"{paper_id}_summary.md"))


def _load_paper_context(user_id: int, paper_id: str, data_source: str) -> str:
    """
    Build paper context string to be injected into the system prompt.

    For user-uploaded papers (up_* prefix), falls back to stored summary/abstract.
    For regular papers, tries file_collect content then falls back to structured data.
    """
    is_user_paper = paper_id.startswith("up_")

    if is_user_paper:
        ups = _get_user_paper_service()
        paper = ups.get_paper(user_id, paper_id)
        if not paper:
            return ""
        parts = []
        if paper.get("title"):
            parts.append(f"标题：{paper['title']}")
        if paper.get("abstract"):
            parts.append(f"\n摘要：{paper['abstract']}")
        if paper.get("summary_json"):
            try:
                summary = json.loads(paper["summary_json"])
                if isinstance(summary, dict):
                    intro = summary.get("🛎️文章简介", {})
                    if isinstance(intro, dict):
                        parts.append(f"\n研究问题：{intro.get('🔸研究问题', '')}")
                        parts.append(f"主要贡献：{intro.get('🔸主要贡献', '')}")
                    methods = summary.get("📝重点思路", [])
                    if methods:
                        parts.append("\n重点思路：\n" + "\n".join(f"- {m}" for m in methods))
                    findings = summary.get("🔎分析总结", [])
                    if findings:
                        parts.append("\n分析总结：\n" + "\n".join(f"- {f}" for f in findings))
            except Exception:
                pass
        return "\n".join(parts)

    # Regular paper from file_collect
    content = _load_paper_content(paper_id, data_source)
    if content:
        return content

    # Fallback: structured data from data_service
    ds = _get_data_service()
    detail = ds.get_paper_detail(paper_id, user_id=user_id)
    if not detail:
        return ""
    s = detail.get("summary", {})
    parts = []
    if s.get("📖标题"):
        parts.append(f"标题：{s['📖标题']}")
    if s.get("abstract"):
        parts.append(f"\n摘要：{s['abstract']}")
    intro = s.get("🛎️文章简介", {})
    if isinstance(intro, dict):
        parts.append(f"\n研究问题：{intro.get('🔸研究问题', '')}")
        parts.append(f"主要贡献：{intro.get('🔸主要贡献', '')}")
    methods = s.get("📝重点思路", [])
    if methods:
        parts.append("\n重点思路：\n" + "\n".join(f"- {m}" for m in methods))
    findings = s.get("🔎分析总结", [])
    if findings:
        parts.append("\n分析总结：\n" + "\n".join(f"- {f}" for f in findings))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _approx_tokens(text: str) -> int:
    return int(len(text) * 0.6) if text else 0


def _crop(text: str, budget: int) -> str:
    char_limit = int(budget / 0.6)
    return text if len(text) <= char_limit else text[:char_limit]


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def get_or_create_session(user_id: int, paper_id: str) -> dict:
    """Return the existing session or create a new one for user + paper."""
    now = _now_iso()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, user_id, paper_id, created_at, updated_at, "
            "context_summary, summary_up_to_msg_id "
            "FROM paper_chat_sessions WHERE user_id = ? AND paper_id = ?",
            (user_id, paper_id),
        ).fetchone()
        if row:
            return dict(row)
        conn.execute(
            "INSERT INTO paper_chat_sessions "
            "(user_id, paper_id, created_at, updated_at, context_summary, summary_up_to_msg_id) "
            "VALUES (?, ?, ?, ?, '', 0)",
            (user_id, paper_id, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, user_id, paper_id, created_at, updated_at, "
            "context_summary, summary_up_to_msg_id "
            "FROM paper_chat_sessions WHERE user_id = ? AND paper_id = ?",
            (user_id, paper_id),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_messages(user_id: int, paper_id: str) -> list[dict]:
    """Return all non-system messages for a user+paper session (oldest first)."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id FROM paper_chat_sessions WHERE user_id = ? AND paper_id = ?",
            (user_id, paper_id),
        ).fetchone()
        if not row:
            return []
        session_id = row["id"]
        rows = conn.execute(
            "SELECT id, role, content, created_at FROM paper_chat_messages "
            "WHERE session_id = ? AND role != 'system' ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_message(session_id: int, role: str, content: str) -> dict:
    """Persist a single message and return the saved row."""
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO paper_chat_messages (session_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, role, content, now),
        )
        conn.execute(
            "UPDATE paper_chat_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, role, content, created_at FROM paper_chat_messages "
            "WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def clear_session(user_id: int, paper_id: str) -> None:
    """Delete all messages for a user+paper session and reset summary state."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id FROM paper_chat_sessions WHERE user_id = ? AND paper_id = ?",
            (user_id, paper_id),
        ).fetchone()
        if row:
            conn.execute(
                "DELETE FROM paper_chat_messages WHERE session_id = ?",
                (row["id"],),
            )
            conn.execute(
                "UPDATE paper_chat_sessions "
                "SET updated_at = ?, context_summary = '', summary_up_to_msg_id = 0 "
                "WHERE id = ?",
                (_now_iso(), row["id"]),
            )
            conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Context strategy helpers
# ---------------------------------------------------------------------------

def _update_session_summary(conn: sqlite3.Connection, session_id: int,
                             summary: str, up_to_msg_id: int) -> None:
    conn.execute(
        "UPDATE paper_chat_sessions SET context_summary = ?, summary_up_to_msg_id = ? "
        "WHERE id = ?",
        (summary, up_to_msg_id, session_id),
    )
    conn.commit()


def _compress_to_summary(
    messages_to_compress: list[dict],
    existing_summary: str,
    client: OpenAI,
    model: str,
) -> str:
    """
    Synchronous (non-streaming) LLM call to compress old messages into a summary.
    Returns the new summary text, or the existing summary on failure.
    """
    if not messages_to_compress:
        return existing_summary

    lines = []
    if existing_summary:
        lines.append(f"[已有摘要]\n{existing_summary}\n")
    lines.append("[需要压缩的新对话]")
    for m in messages_to_compress:
        role_label = "用户" if m["role"] == "user" else "助手"
        lines.append(f"{role_label}：{m['content']}")

    compress_prompt = (
        "请将以下对话历史压缩为一段简短的中文摘要（200字以内），"
        "保留关键问题、重要结论和专有名词，忽略寒暄和重复内容。"
        "只输出摘要正文，不要任何前言或格式标记。"
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": compress_prompt},
                {"role": "user", "content": "\n".join(lines)},
            ],
            stream=False,
            max_tokens=512,
            temperature=0.3,
        )
        return resp.choices[0].message.content or existing_summary
    except Exception:
        return existing_summary


def _build_context_messages(
    session_id: int,
    session: dict,
    cfg: dict,
    system_content: str,
    client: OpenAI,
    model: str,
) -> list[dict]:
    """
    Build the full messages list to send to the LLM based on the chosen
    context_strategy.

    Returns a list of OpenAI-style message dicts.
    """
    strategy = (cfg.get("context_strategy") or "recent_k").strip()
    k = max(1, int(cfg.get("context_k", 10)))

    # Token budget for history (system prompt already occupies some budget)
    hard_limit = int(cfg.get("input_hard_limit", 129024))
    safety_margin = int(cfg.get("input_safety_margin", 4096))
    budget = max(1, hard_limit - safety_margin - _approx_tokens(system_content))

    conn = _connect()
    try:
        if strategy == "recent_k":
            # Fetch the most recent 2*K non-system messages, then reverse
            rows = conn.execute(
                "SELECT role, content FROM paper_chat_messages "
                "WHERE session_id = ? AND role != 'system' "
                "ORDER BY created_at DESC LIMIT ?",
                (session_id, 2 * k),
            ).fetchall()
            history = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

        elif strategy == "summary":
            cutoff_id = int(session.get("summary_up_to_msg_id") or 0)
            existing_summary = session.get("context_summary") or ""

            # All messages not yet covered by the summary
            unsummarised_rows = conn.execute(
                "SELECT id, role, content FROM paper_chat_messages "
                "WHERE session_id = ? AND role != 'system' AND id > ? "
                "ORDER BY created_at ASC",
                (session_id, cutoff_id),
            ).fetchall()
            unsummarised = [{"id": r["id"], "role": r["role"], "content": r["content"]}
                            for r in unsummarised_rows]

            # If unsummarised messages exceed 2*K, compress the oldest surplus
            if len(unsummarised) > 2 * k:
                to_compress = unsummarised[: len(unsummarised) - 2 * k]
                recent = unsummarised[len(unsummarised) - 2 * k:]
                new_summary = _compress_to_summary(to_compress, existing_summary, client, model)
                new_cutoff = to_compress[-1]["id"]
                _update_session_summary(conn, session_id, new_summary, new_cutoff)
                existing_summary = new_summary
                history = [{"role": m["role"], "content": m["content"]} for m in recent]
            else:
                history = [{"role": m["role"], "content": m["content"]} for m in unsummarised]

            # Prepend summary as a system-level context message
            messages: list[dict] = [{"role": "system", "content": system_content}]
            if existing_summary:
                messages.append({
                    "role": "system",
                    "content": f"[对话历史摘要]\n{existing_summary}",
                })
            messages.extend(history)
            return messages

        else:  # "full"
            rows = conn.execute(
                "SELECT role, content FROM paper_chat_messages "
                "WHERE session_id = ? AND role != 'system' "
                "ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
            history = [{"role": r["role"], "content": r["content"]} for r in rows]

    finally:
        conn.close()

    # For recent_k and full: trim from oldest if over token budget
    history = list(history)  # ensure it's a copy, not a reference
    history_tokens = sum(_approx_tokens(m["content"]) for m in history)
    while history and history_tokens > budget:
        removed = history.pop(0)
        history_tokens -= _approx_tokens(removed["content"])

    return [{"role": "system", "content": system_content}] + history


# ---------------------------------------------------------------------------
# Streaming generator
# ---------------------------------------------------------------------------

def stream_chat(
    user_id: int,
    paper_id: str,
    user_message: str,
    input_multiplier: float = 1.0,
) -> Generator[str, None, None]:
    """
    Generator that yields SSE-formatted strings:
        data: <chunk>\\n\\n
    with a final:
        data: [DONE]\\n\\n

    Flow:
    1. Load user settings (feature="paper_chat") for LLM configuration.
    2. Get or create session; persist the user message.
    3. Build messages array using the configured context strategy.
    4. Stream LLM response; persist the complete assistant reply when done.

    Args:
        input_multiplier: Engagement boost multiplier applied to `input_hard_limit`.
            Values > 1.0 allow the model to read more paper context in a single turn.
    """
    us = _get_user_settings_service()
    ups = _get_user_presets_service()
    cfg = us.get_settings(user_id, "paper_chat")

    # Override LLM params from preset if selected
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

    # Override system prompt from prompt preset if selected
    prompt_preset_id = cfg.get("prompt_preset_id")
    if prompt_preset_id:
        p_preset = ups.get_prompt_preset(user_id, int(prompt_preset_id))
        if p_preset and p_preset.get("prompt_content"):
            cfg["system_prompt"] = p_preset["prompt_content"]

    # Apply engagement boost multiplier to input context window
    if input_multiplier > 1.0:
        base_limit = int(cfg.get("input_hard_limit", 129024))
        cfg["input_hard_limit"] = int(base_limit * input_multiplier)

    llm_url = (cfg.get("llm_base_url") or "").strip()
    llm_key = (cfg.get("llm_api_key") or "").strip()
    llm_model = (cfg.get("llm_model") or "").strip()

    if not llm_url or not llm_key or not llm_model:
        yield f"data: {json.dumps('请先在「个人中心 → AI 问答」中配置 LLM 的 URL、API Key 和 Model，或选择一个模型预设。', ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    # Get/create session and persist user message
    session = get_or_create_session(user_id, paper_id)
    session_id = session["id"]
    add_message(session_id, "user", user_message)

    # Reload session to get latest state (summary fields etc.)
    conn = _connect()
    try:
        session_row = conn.execute(
            "SELECT id, context_summary, summary_up_to_msg_id "
            "FROM paper_chat_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        session = dict(session_row) if session_row else session
    finally:
        conn.close()

    # Build system prompt with paper context
    base_system_prompt = (cfg.get("system_prompt") or "").strip()
    if not base_system_prompt:
        defaults = us.get_defaults("paper_chat")
        base_system_prompt = defaults.get("system_prompt", "")

    data_source = (cfg.get("data_source") or "summary").strip()
    if data_source not in ("full_text", "abstract", "summary"):
        data_source = "summary"

    if paper_id == GENERAL_CHAT_PAPER_ID:
        system_content = base_system_prompt
        if not system_content:
            defaults = us.get_defaults("paper_chat")
            system_content = (defaults.get("system_prompt") or "").strip()
        if not system_content:
            system_content = "你是一个专业、友好的学术与通用助手。"
        system_content = (
            system_content
            + "\n\n当前为「通用助手」模式：用户未绑定单篇论文，请直接、清晰回答用户问题；"
            "若问题与某篇论文强相关，可建议用户打开该论文后再使用论文问答。"
        )
    else:
        paper_context = _load_paper_context(user_id, paper_id, data_source)
        if paper_context:
            system_content = (
                base_system_prompt
                + "\n\n---\n以下是本次问答所针对的论文内容：\n\n"
                + paper_context
            )
        else:
            system_content = base_system_prompt

    # Build LLM client (needed by summary strategy for compression)
    client = OpenAI(api_key=llm_key, base_url=llm_url)

    # Build context messages using the configured strategy
    messages = _build_context_messages(session_id, session, cfg, system_content, client, llm_model)

    # Stream LLM response
    full_reply = ""
    try:
        kwargs: dict = {}
        temperature = cfg.get("temperature")
        if temperature is not None:
            kwargs["temperature"] = float(temperature)
        max_tokens = cfg.get("max_tokens")
        if max_tokens is not None:
            kwargs["max_tokens"] = int(max_tokens)

        response = client.chat.completions.create(
            model=llm_model,
            messages=messages,
            stream=True,
            **kwargs,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                full_reply += text
                yield f"data: {json.dumps(text, ensure_ascii=False)}\n\n"

    except Exception as exc:
        error_msg = f"问答失败: {exc}"
        yield f"data: {json.dumps(error_msg, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        return

    # Persist the complete assistant reply
    if full_reply:
        add_message(session_id, "assistant", full_reply)

    yield "data: [DONE]\n\n"


# Ensure tables exist on import
init_db()
