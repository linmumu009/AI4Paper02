"""
Weekly Recap Service — Sunday Recap MVP.

Generates a structured Chinese research-narrative recap from the papers a user
saved to their knowledge base in the past 7 days.  The result is cached in
``weekly_recaps`` so the same week is only generated once (unless the user
explicitly forces a refresh).

Database tables (created by init_db):
  weekly_recaps:
    id, user_id, week_start, week_end, paper_ids_json,
    recap_json, status, created_at, updated_at
  (unique index: user_id + week_start)

Recap JSON schema:
  {
    "title":               str,          # e.g. "本周你关注了 RLHF 与 reward hacking"
    "summary":             str,          # one-sentence overview
    "paper_count":         int,
    "themes": [
      {
        "name":      str,
        "paper_ids": [str, ...],
        "insight":   str                # what these papers share
      }
    ],
    "connections":         [str, ...],   # cross-paper narrative threads
    "recommended_revisit": [str, ...],   # paper_ids worth re-reading
    "next_questions":      [str, ...]    # questions worth pursuing next
  }
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")

# Minimum saved papers to attempt an LLM recap
MIN_PAPERS_FOR_RECAP = 3

# Recap window (days)
RECAP_WINDOW_DAYS = 7


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Create weekly_recaps table if it does not exist."""
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weekly_recaps (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                week_start      TEXT    NOT NULL,
                week_end        TEXT    NOT NULL,
                paper_ids_json  TEXT    NOT NULL DEFAULT '[]',
                recap_json      TEXT    NOT NULL DEFAULT '{}',
                status          TEXT    NOT NULL DEFAULT 'pending',
                created_at      TEXT    NOT NULL,
                updated_at      TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_wr_user_week
                ON weekly_recaps(user_id, week_start)
        """)
        conn.commit()
        logger.info("recap_service: DB tables ready")
    except Exception as exc:
        logger.error("recap_service.init_db: %r", exc)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Week boundaries
# ---------------------------------------------------------------------------

def _week_bounds(now: datetime) -> tuple[str, str]:
    """Return (week_start, week_end) ISO date strings for the current week (Mon–Sun).

    If today is Sunday, we return the week that just ended today so users see a
    full Sunday Recap on the day it is generated.
    """
    # Monday = 0, Sunday = 6
    weekday = now.weekday()
    monday = (now - timedelta(days=weekday)).date()
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def _previous_week_bounds(now: datetime) -> tuple[str, str]:
    """Return week bounds for the previous (last) 7-day window before now."""
    end = (now - timedelta(days=1)).date()
    start = (now - timedelta(days=RECAP_WINDOW_DAYS)).date()
    return start.isoformat(), end.isoformat()


def get_recap_window(now: Optional[datetime] = None) -> tuple[str, str]:
    """Return the window we should try to generate a recap for.

    Logic:
    - If today is Sunday (weekday==6): use the current Mon–Sun week (today included).
    - Otherwise: use the previous 7-day rolling window.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.weekday() == 6:
        return _week_bounds(now)
    return _previous_week_bounds(now)


# ---------------------------------------------------------------------------
# KB paper fetching
# ---------------------------------------------------------------------------

def _get_saved_papers(user_id: int, start_iso: str, end_iso: str) -> list[dict]:
    """Return list of paper data dicts saved by user in [start, end] date range."""
    conn = _connect()
    try:
        # end_iso is a date; add one day to make it inclusive via < comparison
        end_dt = datetime.fromisoformat(end_iso)
        end_exclusive = (end_dt + timedelta(days=1)).date().isoformat()

        rows = conn.execute(
            """
            SELECT paper_id, paper_data, created_at
            FROM kb_papers
            WHERE user_id = ? AND scope = 'kb'
              AND DATE(created_at) >= ? AND DATE(created_at) < ?
            ORDER BY created_at ASC
            """,
            (user_id, start_iso, end_exclusive),
        ).fetchall()

        papers = []
        for row in rows:
            try:
                data = json.loads(row["paper_data"] or "{}")
            except Exception:
                data = {}
            data["_paper_id"] = row["paper_id"]
            data["_saved_at"] = row["created_at"]
            papers.append(data)
        return papers
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# LLM config resolution
# ---------------------------------------------------------------------------

def _get_llm_config(user_id: int) -> Optional[dict]:
    """Load LLM config for recap generation.

    Priority: paper_chat settings → deep_research settings.
    Returns None if no credentials and pool is not active.
    Includes ``use_openrouter_free_pool`` for pool-aware client creation.
    """
    try:
        from services import user_settings_service as _uss
        from services import user_presets_service as _ups
        from services.llm_client_factory import has_llm_credentials

        cfg = _uss.get_settings(user_id, "paper_chat")

        if not ((cfg.get("llm_preset_id") or "").strip() or (cfg.get("llm_model") or "").strip()):
            cfg = _uss.get_settings(user_id, "deep_research")

        preset_id = (cfg.get("llm_preset_id") or "").strip()
        enable_thinking = False
        use_pool = False
        if preset_id:
            preset = _ups.get_llm_preset(user_id, int(preset_id))
            if preset:
                cfg["llm_base_url"] = preset.get("base_url", "")
                cfg["llm_api_key"] = preset.get("api_key", "")
                cfg["llm_model"] = preset.get("model", "")
                enable_thinking = bool(preset.get("enable_thinking", False))
                use_pool = bool(preset.get("use_openrouter_free_pool", False))

        model = (cfg.get("llm_model") or "").strip()
        api_key = (cfg.get("llm_api_key") or "").strip()
        base_url = (cfg.get("llm_base_url") or "").strip()
        if cfg.get("use_openrouter_free_pool") is not None and not use_pool:
            use_pool = bool(cfg["use_openrouter_free_pool"])

        result = {
            "llm_base_url": base_url,
            "llm_api_key": api_key,
            "llm_model": model,
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "max_tokens": int(cfg.get("max_tokens") or 2048),
            "temperature": float(cfg.get("temperature") or 0.5),
            "enable_thinking": enable_thinking,
            "use_openrouter_free_pool": use_pool,
        }

        if not has_llm_credentials(result):
            return None

        return result
    except Exception as exc:
        logger.warning("recap_service._get_llm_config: %r", exc)
        return None


# ---------------------------------------------------------------------------
# Simple keyword-based clustering (no vectors needed for MVP)
# ---------------------------------------------------------------------------

def _extract_keywords(paper: dict) -> list[str]:
    """Return coarse topic tokens from a paper dict."""
    import re
    cats: list[str] = paper.get("categories") or []
    title_en: str = (paper.get("short_title") or paper.get("title") or "")
    abstract: str = (paper.get("abstract") or "")

    _STOP = frozenset({
        "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of",
        "with", "by", "is", "was", "are", "we", "our", "this", "that",
        "these", "those", "paper", "work", "new", "large", "via", "based",
        "using", "novel", "show", "shows", "propose", "present", "method",
    })
    tokens = [
        w.lower() for w in re.findall(r"[a-zA-Z][a-zA-Z0-9\-']*", f"{title_en} {abstract}")
        if len(w) >= 4 and w.lower() not in _STOP
    ]
    return list(set(cats[:3] + tokens[:20]))


def _cluster_papers(papers: list[dict]) -> list[dict]:
    """Group papers into rough theme clusters based on shared categories/keywords.

    Returns a list of clusters:
      [{"paper_ids": [...], "shared_tokens": [...]}]
    """
    if not papers:
        return []

    # Map paper_id → tokens
    pid_to_tokens: dict[str, list[str]] = {}
    for p in papers:
        pid = p.get("_paper_id") or p.get("paper_id", "?")
        pid_to_tokens[pid] = _extract_keywords(p)

    # Token → papers
    token_to_pids: dict[str, list[str]] = defaultdict(list)
    for pid, tokens in pid_to_tokens.items():
        for tok in tokens:
            token_to_pids[tok].append(pid)

    # Sort tokens by how many papers share them
    ranked_tokens = sorted(token_to_pids.items(), key=lambda x: -len(x[1]))

    assigned: set[str] = set()
    clusters: list[dict] = []
    for token, pids in ranked_tokens:
        members = [p for p in pids if p not in assigned and len(pids) >= 2]
        if len(members) >= 2:
            for pid in members:
                assigned.add(pid)
            clusters.append({"paper_ids": members, "shared_tokens": [token]})
        if len(clusters) >= 4:
            break

    # Remaining papers → misc cluster
    remainder = [p.get("_paper_id") or p.get("paper_id", "?") for p in papers if (p.get("_paper_id") or p.get("paper_id", "?")) not in assigned]
    if remainder:
        clusters.append({"paper_ids": remainder, "shared_tokens": []})

    return clusters


# ---------------------------------------------------------------------------
# LLM generation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
你是一位资深 AI 科研助手，擅长帮助研究人员梳理和理解学术论文之间的脉络关系。

用户会提供一批他们最近收藏的论文信息（标题、摘要、分类、机构）。\
你需要生成一份简洁、有洞见的研究回顾总结，帮助用户从宏观视角理解这些论文之间的联系和研究趋势。

你的输出必须是严格的 JSON 格式（不要加 markdown 代码块，直接输出 JSON），结构如下：
{
  "title": "一句话描述本周核心研究主题（不超过25字，要有主题词）",
  "summary": "一段话总览本周收藏（2-3句，突出研究价值）",
  "themes": [
    {
      "name": "主题名称（5-10字）",
      "paper_ids": ["paper_id1", "paper_id2"],
      "insight": "这些论文共同在探讨什么，以及它们如何相互关联（2-3句）"
    }
  ],
  "connections": [
    "跨主题论文之间的叙事联系（每条1-2句，可以是\"A提出问题，B给出解法\"这类）"
  ],
  "recommended_revisit": ["最值得重读的paper_id1", "paper_id2"],
  "next_questions": [
    "根据这些论文，接下来值得追问的研究问题（每条1句）"
  ]
}

规则：
- themes 最多4个，每个至少含1篇论文的paper_id
- connections 最多3条（如果论文太少或没有跨主题联系可以为空数组）
- recommended_revisit 最多2个paper_id（选最核心的）
- next_questions 最多3条
- 所有paper_ids必须是用户提供的真实paper_id
- 输出纯JSON，不要任何额外文字
"""


def _build_user_message(papers: list[dict], clusters: list[dict]) -> str:
    """Build the user message for the LLM."""
    parts = [f"以下是我本周收藏的 {len(papers)} 篇论文：\n"]

    # Build id → paper map
    pid_map = {
        (p.get("_paper_id") or p.get("paper_id", "?")): p
        for p in papers
    }

    for i, p in enumerate(papers, 1):
        pid = p.get("_paper_id") or p.get("paper_id", "?")
        title_cn = p.get("📖标题") or p.get("title") or p.get("short_title") or "无标题"
        title_en = p.get("short_title") or ""
        abstract = (p.get("abstract") or "")[:300]
        categories = ", ".join(p.get("categories") or [])
        institution = p.get("institution") or ""
        parts.append(
            f"[{i}] paper_id: {pid}\n"
            f"  标题(中): {title_cn}\n"
            f"  标题(英): {title_en}\n"
            f"  分类: {categories}\n"
            f"  机构: {institution}\n"
            f"  摘要: {abstract}\n"
        )

    if clusters:
        parts.append("\n初步主题聚类（供参考，可自行调整）：")
        for j, cl in enumerate(clusters, 1):
            tokens = ", ".join(cl.get("shared_tokens") or [])
            parts.append(f"  聚类{j}: {cl['paper_ids']} (关键词: {tokens or '无'})")

    parts.append("\n请生成 JSON 格式的研究回顾。")
    return "\n".join(parts)


def _generate_recap_with_llm(user_id: int, papers: list[dict]) -> Optional[dict]:
    """Call LLM and return parsed recap dict, or None on failure."""
    cfg = _get_llm_config(user_id)
    if not cfg:
        logger.info("recap_service: no LLM config for user %d", user_id)
        return None

    clusters = _cluster_papers(papers)
    user_msg = _build_user_message(papers, clusters)

    try:
        from services.llm_request_options import build_thinking_kwargs
        from services.llm_client_factory import build_llm_client
        client = build_llm_client(cfg)
        _extra = build_thinking_kwargs(cfg)
        response = client.chat.completions.create(
            model=cfg["llm_model"],
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=cfg["max_tokens"],
            temperature=cfg["temperature"],
            **_extra,
        )
        content = (response.choices[0].message.content or "").strip()
        # Strip markdown code fences if any
        if content.startswith("```"):
            content = "\n".join(
                line for line in content.splitlines()
                if not line.strip().startswith("```")
            ).strip()
        return json.loads(content)
    except json.JSONDecodeError as exc:
        logger.warning("recap_service: LLM returned non-JSON: %r", exc)
        return None
    except Exception as exc:
        logger.error("recap_service._generate_recap_with_llm: %r", exc)
        return None


# ---------------------------------------------------------------------------
# Cache CRUD
# ---------------------------------------------------------------------------

def _get_cached_recap(user_id: int, week_start: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM weekly_recaps WHERE user_id = ? AND week_start = ?",
            (user_id, week_start),
        ).fetchone()
        if row is None:
            return None
        r = dict(row)
        r["paper_ids"] = json.loads(r.pop("paper_ids_json", "[]"))
        try:
            r["recap"] = json.loads(r.pop("recap_json", "{}"))
        except Exception:
            r["recap"] = {}
        return r
    finally:
        conn.close()


def _upsert_recap(user_id: int, week_start: str, week_end: str,
                  paper_ids: list[str], recap: dict, status: str) -> None:
    conn = _connect()
    try:
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO weekly_recaps
                (user_id, week_start, week_end, paper_ids_json, recap_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, week_start) DO UPDATE SET
                week_end       = excluded.week_end,
                paper_ids_json = excluded.paper_ids_json,
                recap_json     = excluded.recap_json,
                status         = excluded.status,
                updated_at     = excluded.updated_at
            """,
            (
                user_id, week_start, week_end,
                json.dumps(paper_ids, ensure_ascii=False),
                json.dumps(recap, ensure_ascii=False),
                status, now, now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_recap_status_summary(user_id: int, now: Optional[datetime] = None) -> dict:
    """Return current week's recap status without triggering LLM generation.

    Used by the research radar panel to display a lightweight status badge.
    Returns:
      { "status": str, "paper_count": int, "week_start": str, "week_end": str }
    where status is one of "ok" | "insufficient_papers" | "no_llm_config" | "error" | "none".
    """
    if now is None:
        now = datetime.now(timezone.utc)
    week_start, week_end = get_recap_window(now)
    papers = _get_saved_papers(user_id, week_start, week_end)
    cached = _get_cached_recap(user_id, week_start)
    status = cached["status"] if cached else "none"
    return {
        "status": status,
        "paper_count": len(papers),
        "week_start": week_start,
        "week_end": week_end,
    }


def get_or_generate_recap(user_id: int, force: bool = False,
                           now: Optional[datetime] = None) -> dict:
    """Return the current week's recap for a user.

    If a cached recap exists (and force=False), return it immediately.
    Otherwise fetch KB papers, generate via LLM, cache, and return.

    Return shape:
      {
        "status":       "ok" | "insufficient_papers" | "no_llm_config" | "generating" | "error",
        "week_start":   str,
        "week_end":     str,
        "paper_count":  int,
        "recap":        dict | None,
        "papers":       [{"paper_id": ..., "title": ..., "saved_at": ...}, ...]
      }
    """
    if now is None:
        now = datetime.now(timezone.utc)

    week_start, week_end = get_recap_window(now)

    # Return cached if not forced
    if not force:
        cached = _get_cached_recap(user_id, week_start)
        if cached and cached.get("status") in ("ok", "insufficient_papers", "no_llm_config"):
            papers = _get_saved_papers(user_id, week_start, week_end)
            return _build_response(cached["status"], week_start, week_end, papers, cached.get("recap"))

    # Fetch papers for the window
    papers = _get_saved_papers(user_id, week_start, week_end)
    paper_ids = [p.get("_paper_id") or p.get("paper_id", "?") for p in papers]

    if len(papers) < MIN_PAPERS_FOR_RECAP:
        _upsert_recap(user_id, week_start, week_end, paper_ids, {}, "insufficient_papers")
        return _build_response("insufficient_papers", week_start, week_end, papers, None)

    cfg = _get_llm_config(user_id)
    if cfg is None:
        _upsert_recap(user_id, week_start, week_end, paper_ids, {}, "no_llm_config")
        return _build_response("no_llm_config", week_start, week_end, papers, None)

    # Generate
    recap = _generate_recap_with_llm(user_id, papers)
    if recap is None:
        _upsert_recap(user_id, week_start, week_end, paper_ids, {}, "error")
        return _build_response("error", week_start, week_end, papers, None)

    # Inject paper_count
    recap["paper_count"] = len(papers)
    _upsert_recap(user_id, week_start, week_end, paper_ids, recap, "ok")
    return _build_response("ok", week_start, week_end, papers, recap)


def _build_response(status: str, week_start: str, week_end: str,
                    papers: list[dict], recap: Optional[dict]) -> dict:
    paper_summaries = [
        {
            "paper_id": p.get("_paper_id") or p.get("paper_id", "?"),
            "title": p.get("📖标题") or p.get("short_title") or p.get("title") or "未知标题",
            "title_en": p.get("short_title") or "",
            "institution": p.get("institution") or "",
            "categories": p.get("categories") or [],
            "saved_at": p.get("_saved_at") or "",
        }
        for p in papers
    ]
    return {
        "status": status,
        "week_start": week_start,
        "week_end": week_end,
        "paper_count": len(papers),
        "recap": recap,
        "papers": paper_summaries,
    }


# ---------------------------------------------------------------------------
# Review cards (Phase 2: spaced review)
# ---------------------------------------------------------------------------

# SRS-lite intervals in days: when a paper was saved this many days ago
_REVIEW_INTERVALS = [7, 30, 90]

# How many days tolerance around each interval (±)
_REVIEW_TOLERANCE = 3


def _ensure_review_state_table() -> None:
    """Create paper_review_state table if it does not exist (lazy migration)."""
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_review_state (
                user_id         INTEGER NOT NULL,
                paper_id        TEXT    NOT NULL,
                last_reviewed_at TEXT,
                review_count    INTEGER NOT NULL DEFAULT 0,
                last_response   TEXT,
                next_due_at     TEXT,
                created_at      TEXT    NOT NULL,
                updated_at      TEXT    NOT NULL,
                PRIMARY KEY (user_id, paper_id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def get_review_cards(user_id: int, limit: int = 3,
                     now: Optional[datetime] = None) -> list[dict]:
    """Return papers saved ~7/30/90 days ago that are due for review.

    Excludes:
    - Papers dismissed forever (last_response='dismiss_forever')
    - Papers reviewed in the last 24 hours
    - Papers with incomplete paper_data

    Returns list of paper summary dicts with extra fields:
      card_kind='review', review_reason, days_since_saved, saved_at
    """
    _ensure_review_state_table()

    if now is None:
        now = datetime.now(timezone.utc)

    recent_cutoff = (now - timedelta(hours=24)).isoformat()
    conn = _connect()
    try:
        candidates = []
        for interval in _REVIEW_INTERVALS:
            low = (now - timedelta(days=interval + _REVIEW_TOLERANCE)).date().isoformat()
            high = (now - timedelta(days=interval - _REVIEW_TOLERANCE)).date().isoformat()

            rows = conn.execute(
                """
                SELECT kb.paper_id, kb.paper_data, kb.created_at AS saved_at
                FROM kb_papers kb
                LEFT JOIN paper_review_state rs
                  ON rs.user_id = kb.user_id AND rs.paper_id = kb.paper_id
                WHERE kb.user_id = ? AND kb.scope = 'kb'
                  AND DATE(kb.created_at) BETWEEN ? AND ?
                  AND (rs.last_response IS NULL OR rs.last_response != 'dismiss_forever')
                  AND (rs.last_reviewed_at IS NULL OR rs.last_reviewed_at < ?)
                ORDER BY kb.created_at DESC
                LIMIT 5
                """,
                (user_id, low, high, recent_cutoff),
            ).fetchall()

            for row in rows:
                try:
                    data = json.loads(row["paper_data"] or "{}")
                except Exception:
                    continue
                if not (data.get("short_title") or data.get("title") or data.get("📖标题")):
                    continue
                saved_dt = datetime.fromisoformat(row["saved_at"].replace("Z", "+00:00"))
                days_ago = (now.date() - saved_dt.date()).days
                data["_paper_id"] = row["paper_id"]
                data["card_kind"] = "review"
                data["review_reason"] = f"你在 {days_ago} 天前收藏了这篇"
                data["days_since_saved"] = days_ago
                data["saved_at"] = row["saved_at"]
                candidates.append(data)

            if len(candidates) >= limit:
                break

        return candidates[:limit]
    finally:
        conn.close()


def record_review_response(user_id: int, paper_id: str, response: str) -> None:
    """Record user's response to a review card.

    response: 'remember' | 'reread' | 'dismiss_forever' | 'skip'
    """
    _ensure_review_state_table()
    now = _now_iso()
    conn = _connect()
    try:
        # Compute next_due based on response
        if response == "remember":
            # Extend to next interval
            next_due = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        elif response == "reread":
            next_due = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        elif response == "dismiss_forever":
            next_due = None
        else:  # skip
            next_due = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

        conn.execute(
            """
            INSERT INTO paper_review_state
                (user_id, paper_id, last_reviewed_at, review_count, last_response,
                 next_due_at, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(user_id, paper_id) DO UPDATE SET
                last_reviewed_at = excluded.last_reviewed_at,
                review_count     = review_count + 1,
                last_response    = excluded.last_response,
                next_due_at      = excluded.next_due_at,
                updated_at       = excluded.updated_at
            """,
            (user_id, paper_id, now, response, next_due, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def _get_paper_titles(user_id: int, paper_ids: list[str]) -> dict[str, str]:
    """Return {paper_id: display_title} for the given paper_ids from the user's KB."""
    if not paper_ids:
        return {}
    conn = _connect()
    try:
        placeholders = ",".join("?" * len(paper_ids))
        rows = conn.execute(
            f"SELECT paper_id, paper_data FROM kb_papers "
            f"WHERE user_id = ? AND paper_id IN ({placeholders})",
            (user_id, *paper_ids),
        ).fetchall()
        result: dict[str, str] = {}
        for row in rows:
            try:
                data = json.loads(row["paper_data"] or "{}")
            except Exception:
                data = {}
            title = (
                data.get("📖标题")
                or data.get("short_title")
                or data.get("title")
                or ""
            )
            if title:
                result[row["paper_id"]] = title
        return result
    finally:
        conn.close()


def get_reactivation_suggestions(user_id: int, limit: int = 3) -> list[dict]:
    """Return reactivation items derived from the most recent successful recap.

    Tries the current week first; falls back to the most recent historical recap.
    Each item: {kind, title, reason, paper_id}
      kind: 'revisit' | 'question'
    Returns [] when no successful recap exists or recap has no useful content.
    """
    now = datetime.now(timezone.utc)
    week_start, _ = get_recap_window(now)
    cached = _get_cached_recap(user_id, week_start)
    recap_data: Optional[dict] = None
    if cached and cached.get("status") == "ok":
        recap_data = cached.get("recap")

    if not recap_data:
        history = get_recap_history(user_id, limit=1)
        if history:
            recap_data = history[0].get("recap")

    if not recap_data:
        return []

    suggestions: list[dict] = []

    revisit_ids: list[str] = recap_data.get("recommended_revisit") or []
    if revisit_ids:
        pid_to_title = _get_paper_titles(user_id, revisit_ids)
        for pid in revisit_ids[:2]:
            title = pid_to_title.get(pid, "")
            if not title:
                continue
            suggestions.append({
                "kind": "revisit",
                "title": title,
                "reason": "上周回顾建议重读",
                "paper_id": pid,
            })

    questions: list[str] = recap_data.get("next_questions") or []
    for q in questions[:2]:
        suggestions.append({
            "kind": "question",
            "title": q,
            "reason": "上周回顾追问",
            "paper_id": None,
        })

    return suggestions[:limit]


def get_recap_history(user_id: int, limit: int = 12) -> list[dict]:
    """Return past recaps for a user (most recent first)."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, week_start, week_end, paper_ids_json, recap_json, status, created_at, updated_at
            FROM weekly_recaps
            WHERE user_id = ? AND status = 'ok'
            ORDER BY week_start DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        result = []
        for row in rows:
            r = dict(row)
            r["paper_ids"] = json.loads(r.pop("paper_ids_json", "[]"))
            try:
                r["recap"] = json.loads(r.pop("recap_json", "{}"))
            except Exception:
                r["recap"] = {}
            result.append(r)
        return result
    finally:
        conn.close()
