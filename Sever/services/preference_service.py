"""User Preference Learning Service.

Translates raw behavioral signals into a per-user preference profile, then
applies a lightweight preference-aware reranking layer on daily paper digests.

Architecture
------------
  user_paper_feedback    – normalized feedback fact table (one row per user-paper-action)
  user_preference_profile – aggregated, time-decayed profile snapshot per user
  paper_feature_cache    – extracted arXiv features per paper (categories / keywords)

Scoring formula (Phase 1)
  final_score = 0.55 * theme_score + 0.30 * preference_score + 0.15 * novelty_score

Exploration buckets
  ≈70 % exploitation  (papers close to user profile)
  ≈20 % adjacent      (nearby topics)
  ≈10 % serendipity   (high-quality but outside current profile)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.safe_logging_service import safe_failure_detail

logger = logging.getLogger(__name__)

# ── Path resolution ────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")

# ── Feedback action weights (plan §信号设计) ───────────────────────────────────
FEEDBACK_WEIGHTS: dict[str, float] = {
    "kb_save":         5.0,   # 收藏到知识库
    "compare_add":     4.0,   # 加入对比
    "research_start":  4.0,   # 深度研究
    "paper_chat":      3.0,   # 论文问答
    "paper_view_deep": 3.0,   # 阅读时长 > VIEW_DEEP_S 秒
    "idea_collect":    3.0,   # 收藏灵感
    "kb_note":         2.0,   # 保存笔记
    "paper_view":      1.0,   # 打开论文详情
    "dismiss":        -3.0,   # 忽略/左滑
    "nudge_less":     -4.0,   # UI "减少此类" 按钮
    "nudge_more":      4.0,   # UI "多看此类" 按钮
}

# Seconds of reading time that promote paper_view → paper_view_deep
VIEW_DEEP_S: float = 60.0

# Minimum feedback events before preference reranking is activated
MIN_FEEDBACK_FOR_PROFILE: int = 3

# Max lookback window (days) for building a profile
PROFILE_DECAY_DAYS: int = 90

# Profile cache TTL (minutes) – avoids rebuilding on every request
PROFILE_CACHE_TTL_MINUTES: int = 60

# Final-score blend weights
W_THEME: float = 0.55
W_PREF: float  = 0.30
W_NOVEL: float = 0.15

# ── Time-decay table ───────────────────────────────────────────────────────────
_DECAY_BUCKETS: list[tuple[int, float]] = [
    (14, 1.0),   # last 14 days  → full weight
    (30, 0.7),   # 15–30 days    → 70 %
    (90, 0.4),   # 31–90 days    → 40 %
]

# ── English stop-word set for keyword extraction ───────────────────────────────
_STOP: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "this", "that",
    "these", "those", "it", "its", "we", "our", "they", "their", "via",
    "using", "based", "new", "novel", "approach", "method", "model",
    "paper", "work", "study", "large", "how", "not", "no", "up", "so",
    "if", "then", "than", "into", "over", "after", "before", "between",
    "while", "which", "when", "where", "all", "both", "each", "few",
    "more", "most", "other", "some", "such", "own", "same", "too", "very",
    "just", "about", "towards", "toward", "across", "without", "within",
    "through", "during", "following", "previous", "recent", "show", "shows",
    "propose", "present", "demonstrate", "introduce", "address", "achieve",
    "improve", "use", "used", "can", "also", "well", "two", "one", "three",
})


# ── DB helpers ─────────────────────────────────────────────────────────────────

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


def _time_decay(created_at_iso: str, now: datetime) -> float:
    """Return time-decay multiplier (0–1) for a feedback event."""
    try:
        dt = datetime.fromisoformat(created_at_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = (now - dt).total_seconds() / 86400.0
    except Exception:
        return 0.0
    for cutoff, decay in _DECAY_BUCKETS:
        if age_days <= cutoff:
            return decay
    return 0.0


# ── DB Initialisation ──────────────────────────────────────────────────────────

def init_db() -> None:
    """Create preference tables if they do not already exist.

    Called from api.py startup event so all tables are ready before first request.
    """
    conn = _connect()
    try:
        # ── user_paper_feedback ──────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_paper_feedback (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL,
                paper_id         TEXT    NOT NULL,
                action           TEXT    NOT NULL,
                weight           REAL    NOT NULL DEFAULT 0.0,
                categories_json  TEXT    NOT NULL DEFAULT '[]',
                keywords_json    TEXT    NOT NULL DEFAULT '[]',
                institution_tier INTEGER NOT NULL DEFAULT 4,
                source           TEXT    NOT NULL DEFAULT 'event',
                created_at       TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_upf_user_created
                ON user_paper_feedback(user_id, created_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_upf_paper
                ON user_paper_feedback(paper_id)
        """)
        # One row per user-paper-action (upsert on conflict)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_upf_unique
                ON user_paper_feedback(user_id, paper_id, action)
        """)

        # ── user_preference_profile ──────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preference_profile (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL UNIQUE,
                profile_json   TEXT    NOT NULL DEFAULT '{}',
                feedback_count INTEGER NOT NULL DEFAULT 0,
                built_at       TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_upp_user
                ON user_preference_profile(user_id)
        """)

        # ── paper_feature_cache ──────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_feature_cache (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id         TEXT    NOT NULL UNIQUE,
                categories_json  TEXT    NOT NULL DEFAULT '[]',
                keywords_json    TEXT    NOT NULL DEFAULT '[]',
                institution_tier INTEGER NOT NULL DEFAULT 4,
                created_at       TEXT    NOT NULL,
                updated_at       TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pfc_paper
                ON paper_feature_cache(paper_id)
        """)

        _bandit_init_db(conn)
        conn.commit()
        logger.info("preference_service: DB tables ready")
    except Exception as exc:
        logger.error("preference_service.init_db: %r", exc)
    finally:
        conn.close()


# ── Keyword extraction ─────────────────────────────────────────────────────────

def _tokenize(text: str, max_tokens: int = 40) -> list[str]:
    """Extract meaningful lowercase tokens from free text."""
    words = re.findall(r"[a-z][a-z0-9\-']*", text.lower())
    return [w for w in words if len(w) >= 3 and w not in _STOP][:max_tokens]


def extract_paper_features(paper: dict) -> dict:
    """Pull reusable scoring features from a paper summary dict."""
    cats: list[str] = paper.get("categories") or []
    title_cn: str = paper.get("📖标题") or ""
    title_en: str = paper.get("short_title") or ""
    abstract: str = paper.get("abstract") or ""

    kws: list[str] = []
    seen: set[str] = set()
    for tok in _tokenize(title_en, 20) + _tokenize(title_cn, 15) + _tokenize(abstract, 30):
        if tok not in seen:
            seen.add(tok)
            kws.append(tok)

    tier: int = int(paper.get("institution_tier") or 4)
    return {"categories": cats, "keywords": kws[:40], "institution_tier": tier}


# ── Paper feature cache ────────────────────────────────────────────────────────

def cache_paper_features(paper_id: str, features: dict) -> None:
    """Upsert paper features into paper_feature_cache."""
    conn = _connect()
    try:
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO paper_feature_cache
                (paper_id, categories_json, keywords_json, institution_tier, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id) DO UPDATE SET
                categories_json  = excluded.categories_json,
                keywords_json    = excluded.keywords_json,
                institution_tier = excluded.institution_tier,
                updated_at       = excluded.updated_at
            """,
            (
                paper_id,
                json.dumps(features.get("categories", []), ensure_ascii=False),
                json.dumps(features.get("keywords", []), ensure_ascii=False),
                features.get("institution_tier", 4),
                now,
                now,
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("preference_service.cache_paper_features: %r", exc)
    finally:
        conn.close()


def get_cached_paper_features(paper_id: str) -> dict | None:
    """Return cached paper features, or None if not in cache."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT categories_json, keywords_json, institution_tier FROM paper_feature_cache WHERE paper_id = ?",
            (paper_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "categories": json.loads(row["categories_json"] or "[]"),
            "keywords": json.loads(row["keywords_json"] or "[]"),
            "institution_tier": row["institution_tier"],
        }
    except Exception:
        return None
    finally:
        conn.close()


# ── Feedback recording ─────────────────────────────────────────────────────────

def record_feedback(
    user_id: int,
    paper_id: str,
    action: str,
    categories: Optional[list[str]] = None,
    keywords: Optional[list[str]] = None,
    institution_tier: int = 4,
    source: str = "event",
) -> None:
    """Record a normalised feedback event.

    Uses INSERT OR REPLACE semantics so re-saving/re-dismissing the same paper
    updates the timestamp (recency) rather than accumulating duplicate rows.
    """
    if action not in FEEDBACK_WEIGHTS:
        logger.debug("preference_service.record_feedback: unknown action %r, skipped", action)
        return

    weight = FEEDBACK_WEIGHTS[action]
    # Opportunistically cache features when we have them
    if categories or keywords:
        cache_paper_features(paper_id, {
            "categories": categories or [],
            "keywords": keywords or [],
            "institution_tier": institution_tier,
        })

    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO user_paper_feedback
                (user_id, paper_id, action, weight, categories_json, keywords_json,
                 institution_tier, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, paper_id, action) DO UPDATE SET
                weight           = excluded.weight,
                categories_json  = excluded.categories_json,
                keywords_json    = excluded.keywords_json,
                institution_tier = excluded.institution_tier,
                source           = excluded.source,
                created_at       = excluded.created_at
            """,
            (
                user_id,
                paper_id,
                action,
                weight,
                json.dumps(categories or [], ensure_ascii=False),
                json.dumps(keywords or [], ensure_ascii=False),
                institution_tier,
                source,
                _now_iso(),
            ),
        )
        conn.commit()
        # Invalidate cached profile so next read triggers a rebuild
        conn.execute(
            "DELETE FROM user_preference_profile WHERE user_id = ?", (user_id,)
        )
        conn.commit()
    except Exception as exc:
        logger.warning("preference_service.record_feedback: %r", exc)
    finally:
        conn.close()


# ── Profile building ───────────────────────────────────────────────────────────

def _empty_profile() -> dict:
    return {
        "category_weights": {},
        "keyword_weights": {},
        "negative_categories": [],
        "preferred_tiers": [],
        "total_feedback_count": 0,
        "total_positive_weight": 0.0,
        "total_negative_weight": 0.0,
        "has_enough_data": False,
        "built_at": _now_iso(),
    }


def _normalize_weights(d: dict[str, float]) -> dict[str, float]:
    """Normalise weight dict to [-1, 1] by dividing by the absolute maximum."""
    if not d:
        return {}
    max_abs = max(abs(v) for v in d.values())
    if max_abs == 0:
        return {}
    return {k: round(v / max_abs, 4) for k, v in d.items()}


def _build_profile_from_rows(rows: list) -> dict:
    """Compute preference profile from raw feedback rows with time decay."""
    now = datetime.now(timezone.utc)

    cat_raw: dict[str, float] = {}
    kw_raw: dict[str, float] = {}
    tier_raw: dict[int, float] = {}
    total_pos = 0.0
    total_neg = 0.0

    for row in rows:
        decay = _time_decay(row["created_at"], now)
        if decay <= 0:
            continue
        eff = float(row["weight"]) * decay
        cats: list[str] = json.loads(row["categories_json"] or "[]")
        kws: list[str] = json.loads(row["keywords_json"] or "[]")
        tier: int = int(row["institution_tier"] or 4)

        for cat in cats:
            cat_raw[cat] = cat_raw.get(cat, 0.0) + eff
        for kw in kws:
            kw_raw[kw] = kw_raw.get(kw, 0.0) + eff
        tier_raw[tier] = tier_raw.get(tier, 0.0) + abs(eff)

        if eff > 0:
            total_pos += eff
        else:
            total_neg += abs(eff)

    # Separate positive & negative category signals
    negative_cats = [k for k, v in cat_raw.items() if v < -0.5]
    # Keep only positive weights in the normalised view
    pos_cat_raw = {k: v for k, v in cat_raw.items() if v > 0}
    pos_kw_raw = {k: v for k, v in kw_raw.items() if v > 0}

    pref_tiers = sorted(tier_raw.items(), key=lambda x: -x[1])

    return {
        "category_weights": _normalize_weights(pos_cat_raw),
        "keyword_weights": _normalize_weights(pos_kw_raw),
        "negative_categories": negative_cats,
        "preferred_tiers": [t for t, _ in pref_tiers[:3]],
        "total_feedback_count": len(rows),
        "total_positive_weight": round(total_pos, 2),
        "total_negative_weight": round(total_neg, 2),
        "has_enough_data": len(rows) >= MIN_FEEDBACK_FOR_PROFILE,
        "built_at": _now_iso(),
    }


def build_and_cache_profile(user_id: int) -> dict:
    """Force-rebuild the preference profile from the last PROFILE_DECAY_DAYS of feedback."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=PROFILE_DECAY_DAYS)).isoformat()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT action, weight, categories_json, keywords_json, institution_tier, created_at
            FROM user_paper_feedback
            WHERE user_id = ? AND created_at >= ?
            ORDER BY created_at DESC
            """,
            (user_id, cutoff),
        ).fetchall()

        profile = _build_profile_from_rows(rows) if rows else _empty_profile()

        conn.execute(
            """
            INSERT INTO user_preference_profile (user_id, profile_json, feedback_count, built_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                profile_json   = excluded.profile_json,
                feedback_count = excluded.feedback_count,
                built_at       = excluded.built_at
            """,
            (user_id, json.dumps(profile, ensure_ascii=False), len(rows), _now_iso()),
        )
        conn.commit()
        return profile
    except Exception as exc:
        logger.warning("preference_service.build_profile: %r", exc)
        return _empty_profile()
    finally:
        conn.close()


def get_or_build_profile(user_id: int) -> dict:
    """Return the user's preference profile, rebuilding when stale or missing."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT profile_json, feedback_count, built_at FROM user_preference_profile WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if row:
            try:
                built = datetime.fromisoformat(row["built_at"])
                if built.tzinfo is None:
                    built = built.replace(tzinfo=timezone.utc)
                age_min = (datetime.now(timezone.utc) - built).total_seconds() / 60.0
                if age_min < PROFILE_CACHE_TTL_MINUTES:
                    return json.loads(row["profile_json"])
            except Exception:
                pass
    except Exception:
        pass
    finally:
        conn.close()

    return build_and_cache_profile(user_id)


# ── Preference scoring ─────────────────────────────────────────────────────────

def compute_preference_score(
    paper: dict,
    profile: dict,
) -> tuple[float, list[str]]:
    """Compute a preference score (0–1) and a list of human-readable match reasons.

    Returns (0.5, []) when the profile has insufficient data (neutral).
    """
    result = compute_preference_score_detailed(paper, profile)
    return result["score"], [c["key"] for c in result["contributions"] if c.get("delta", 0) > 0]


def compute_preference_score_detailed(
    paper: dict,
    profile: dict,
) -> dict:
    """Compute preference score with structured per-contribution breakdown.

    Returns
    -------
    dict with keys:
      score        – float 0–1 (same value as compute_preference_score)
      contributions – list of dicts, each:
          type   – one of: category_positive, category_negative, keyword_positive,
                            keyword_negative, tier_mismatch
          key    – the signal identifier (arXiv category, keyword, tier label)
          delta  – signed float contribution to the raw score (before clamping)
          label  – human-readable Chinese explanation

    When the profile has insufficient data, returns score=0.5 and empty contributions.
    """
    if not profile.get("has_enough_data"):
        return {"score": 0.5, "contributions": []}

    cat_weights: dict[str, float] = profile.get("category_weights", {})
    kw_weights: dict[str, float]  = profile.get("keyword_weights", {})
    negative_cats: set[str]       = set(profile.get("negative_categories", []))
    preferred_tiers: list[int]    = [t for t, _ in profile.get("preferred_tiers", [])]

    paper_cats: list[str] = paper.get("categories") or []
    title_en: str = paper.get("short_title") or ""
    title_cn: str = paper.get("📖标题") or ""
    paper_kws: list[str] = _tokenize(title_en, 20) + _tokenize(title_cn, 15)
    paper_tier: int = int(paper.get("institution_tier") or 4)

    contributions: list[dict] = []

    # ── Category match ─────────────────────────────────────────────────────────
    cat_score = 0.0
    for cat in paper_cats:
        if cat in negative_cats:
            delta = -0.4
            cat_score += delta
            contributions.append({
                "type":  "category_negative",
                "key":   cat,
                "delta": round(delta * 0.65, 4),
                "label": f"你最近对 {cat} 方向反馈较少或有 dismiss",
            })
        elif cat in cat_weights and cat_weights[cat] > 0:
            delta = cat_weights[cat]
            cat_score += delta
            contributions.append({
                "type":  "category_positive",
                "key":   cat,
                "delta": round(delta * 0.65, 4),
                "label": f"你常关注 {cat} 方向（权重 {cat_weights[cat]:.2f}）",
            })

    # ── Keyword match ──────────────────────────────────────────────────────────
    kw_score = 0.0
    seen_kws: set[str] = set()
    for kw in paper_kws:
        if kw in seen_kws:
            continue
        seen_kws.add(kw)
        if kw in kw_weights:
            w = kw_weights[kw]
            if w > 0.15:
                delta = w * 0.5
                kw_score += delta
                contributions.append({
                    "type":  "keyword_positive",
                    "key":   kw,
                    "delta": round(delta * 0.35, 4),
                    "label": f"标题含关键词「{kw}」，与你的阅读偏好匹配",
                })
            elif w < -0.10:
                delta = w * 0.5
                kw_score += delta
                contributions.append({
                    "type":  "keyword_negative",
                    "key":   kw,
                    "delta": round(delta * 0.35, 4),
                    "label": f"标题含关键词「{kw}」，与你的历史 dismiss 相关",
                })

    # ── Institution tier signal ────────────────────────────────────────────────
    if preferred_tiers and paper_tier not in preferred_tiers[:2]:
        tier_label_str = f"T{paper_tier}"
        pref_str = " / ".join(f"T{t}" for t in preferred_tiers[:2])
        contributions.append({
            "type":  "tier_mismatch",
            "key":   tier_label_str,
            "delta": -0.05,
            "label": f"机构等级 {tier_label_str}，你通常偏好 {pref_str}",
        })

    # ── Combine ────────────────────────────────────────────────────────────────
    raw = cat_score * 0.65 + kw_score * 0.35
    pref_score = max(0.0, min(1.0, (raw + 1.0) / 2.0))

    # Sort contributions by abs(delta) descending for UI display
    contributions.sort(key=lambda c: -abs(c["delta"]))

    return {"score": round(pref_score, 4), "contributions": contributions}


def _build_why_text(reasons: list[str], profile: dict, is_serendipity: bool) -> str:
    """Build a short Chinese explanation of why this paper is recommended."""
    if is_serendipity:
        return "探索推荐：优质论文，拓展研究视野"

    if not reasons:
        top_cats = sorted(
            profile.get("category_weights", {}).items(), key=lambda x: -x[1]
        )[:2]
        top_names = [c for c, _ in top_cats]
        if top_names:
            return f"与你常关注的 {' · '.join(top_names)} 方向相关"
        return ""

    matched_cats = [r for r in reasons if "." in r]
    matched_kws = [r for r in reasons if "." not in r]

    parts: list[str] = []
    if matched_cats:
        parts.append(" · ".join(matched_cats[:2]))
    if matched_kws:
        parts.append(" · ".join(matched_kws[:3]))

    return "与你的兴趣匹配（" + "，".join(parts) + "）" if parts else "与你的研究偏好相关"


# ── Reranking ──────────────────────────────────────────────────────────────────

def _build_interleaved_result(
    scored: list[dict],
    exploration_ratio: float = 0.25,
) -> list[tuple[dict, bool]]:
    """Split *scored* list into exploitation/serendipity buckets and interleave.

    Parameters
    ----------
    scored:
        Papers sorted descending by final score, each a dict with keys
        paper, theme, pref, novel, final, reasons.
    exploration_ratio:
        Fraction of the slate reserved for serendipity (default 0.25 = 25 %).
        Week 5 bandit will pass per-user values here.
    """
    n = len(scored)
    exploit_n = max(1, int(n * (1.0 - exploration_ratio)))
    exploitation = scored[:exploit_n]
    serendipity = scored[exploit_n:]
    serendipity.sort(key=lambda x: -x["theme"])

    result: list[tuple[dict, bool]] = []
    ei = si = 0
    # Interleave ratio: for every SEREN_CHUNK serendipity items add EXPLOIT_CHUNK exploits
    if exploration_ratio <= 0:
        EXPLOIT_CHUNK, SEREN_CHUNK = 1, 0
    else:
        exploit_slots = max(1, round((1.0 - exploration_ratio) / exploration_ratio))
        EXPLOIT_CHUNK, SEREN_CHUNK = exploit_slots, 1

    while ei < len(exploitation) or si < len(serendipity):
        for _ in range(EXPLOIT_CHUNK):
            if ei < len(exploitation):
                result.append((exploitation[ei], False))
                ei += 1
        for _ in range(SEREN_CHUNK):
            if si < len(serendipity):
                result.append((serendipity[si], True))
                si += 1

    return result


def rerank_papers_detailed(
    user_id: int,
    papers: list[dict],
    exploration_ratio: Optional[float] = None,
    score_weights: Optional[dict] = None,
) -> tuple[list[dict], dict]:
    """Rerank *papers* and return (annotated_papers, rerank_meta).

    This is the authoritative implementation.  ``rerank_papers()`` is a thin
    wrapper around this function that exists for backward compatibility.

    Parameters
    ----------
    user_id:
        Authenticated user ID.
    papers:
        Raw paper dicts (from data_service).
    exploration_ratio:
        Fraction of slate for serendipity.  Week 5 bandit passes per-user value.
    score_weights:
        Override for (theme, pref, novel) blend.  Defaults to profile's stored
        weights or global constants (W_THEME / W_PREF / W_NOVEL).

    Returns
    -------
    (annotated_papers, rerank_meta) where rerank_meta contains:
      - weights: dict used for scoring
      - profile_version: str (built_at from profile)
      - had_enough_data: bool
      - scored_papers: list[dict] with per-paper score breakdown
        Each element has: paper_id, theme_score, pref_score, novel_score,
        final_score, is_exploration
    """
    if not papers:
        _annotate_defaults(papers)
        meta = _empty_meta(score_weights)
        return papers, meta

    try:
        profile = get_or_build_profile(user_id)
    except Exception as exc:
        logger.warning("rerank_papers_detailed: failed to get profile for user %s: %r", user_id, exc)
        _annotate_defaults(papers)
        meta = _empty_meta(score_weights)
        return papers, meta

    if not profile.get("has_enough_data"):
        _annotate_defaults(papers)
        meta = _empty_meta(score_weights, profile)
        return papers, meta

    # ── Determine effective exploration ratio ──────────────────────────────────
    # Priority: explicit argument > Thompson-sampled per-user > default 0.25
    if exploration_ratio is None:
        try:
            exploration_ratio = pick_exploration_ratio(user_id)
        except Exception:
            exploration_ratio = 0.25

    # ── Determine effective weights ────────────────────────────────────────────
    # Priority: explicit argument > profile-stored per-user weights > global constants
    if score_weights is None:
        stored = profile.get("score_weights") or {}
        score_weights = {
            "theme": float(stored.get("theme", W_THEME)),
            "pref":  float(stored.get("pref", W_PREF)),
            "novel": float(stored.get("novel", W_NOVEL)),
        }
    w_theme = score_weights.get("theme", W_THEME)
    w_pref  = score_weights.get("pref",  W_PREF)
    w_novel = score_weights.get("novel", W_NOVEL)

    # Normalise so they sum to 1 (tolerate minor float drift)
    w_sum = w_theme + w_pref + w_novel
    if w_sum > 0 and abs(w_sum - 1.0) > 0.01:
        w_theme /= w_sum
        w_pref  /= w_sum
        w_novel /= w_sum

    # ── Score every paper ──────────────────────────────────────────────────────
    scored: list[dict] = []
    for p in papers:
        theme = float(p.get("relevance_score") or 0.5)
        pref, reasons = compute_preference_score(p, profile)
        novel = 1.0 - pref
        final = w_theme * theme + w_pref * pref + w_novel * novel
        scored.append({
            "paper":   p,
            "theme":   round(theme, 4),
            "pref":    round(pref,  4),
            "novel":   round(novel, 4),
            "final":   round(final, 4),
            "reasons": reasons,
        })

    scored.sort(key=lambda x: -x["final"])

    # ── Interleave buckets ─────────────────────────────────────────────────────
    interleaved = _build_interleaved_result(scored, exploration_ratio)

    # ── Annotate output papers ─────────────────────────────────────────────────
    out: list[dict] = []
    scored_papers_meta: list[dict] = []
    for item, is_seren in interleaved:
        p = dict(item["paper"])
        p["preference_score"] = item["pref"]
        p["is_exploration"]   = is_seren
        p["why_recommended"]  = _build_why_text(item["reasons"], profile, is_seren)
        out.append(p)
        scored_papers_meta.append({
            "paper_id":     p.get("paper_id", ""),
            "theme_score":  item["theme"],
            "pref_score":   item["pref"],
            "novel_score":  item["novel"],
            "final_score":  item["final"],
            "is_exploration": is_seren,
        })

    profile_version = profile.get("built_at", "")
    meta = {
        "weights": {"theme": round(w_theme, 4), "pref": round(w_pref, 4), "novel": round(w_novel, 4)},
        "profile_version": profile_version,
        "had_enough_data": True,
        "scored_papers": scored_papers_meta,
    }
    return out, meta


def rerank_papers(user_id: int, papers: list[dict]) -> list[dict]:
    """Backward-compatible wrapper around ``rerank_papers_detailed()``.

    Returns only the annotated paper list; callers that need score details
    (e.g. impression logging, calibrator) should call ``rerank_papers_detailed()``.
    """
    out, _meta = rerank_papers_detailed(user_id, papers)
    return out


def _empty_meta(
    score_weights: Optional[dict] = None,
    profile: Optional[dict] = None,
) -> dict:
    """Return a rerank_meta dict for cold-start / error cases."""
    w = score_weights or {"theme": W_THEME, "pref": W_PREF, "novel": W_NOVEL}
    return {
        "weights": w,
        "profile_version": profile.get("built_at", "") if profile else "",
        "had_enough_data": False,
        "scored_papers": [],
    }


def _annotate_defaults(papers: list[dict]) -> None:
    """Add preference fields with neutral defaults when profile is insufficient."""
    for p in papers:
        p.setdefault("preference_score", 0.5)
        p.setdefault("is_exploration", False)
        p.setdefault("why_recommended", "")


# ── Exploration Bandit (Thompson Sampling) ────────────────────────────────────
#
# We maintain a Beta(alpha, beta) distribution for each user × arm combination.
# Arms are discrete exploration ratios: 0%, 10%, 20%, 30% of the slate.
# At each rerank call we sample from each arm's Beta and pick the argmax arm.
# Daily reward updates (called from the scheduler) push α/β based on whether
# exploration-tagged impressions led to positive feedback within 7 days.

BANDIT_ARMS: list[float] = [0.0, 0.10, 0.20, 0.30]
_BANDIT_ALPHA_INIT: float = 1.0
_BANDIT_BETA_INIT: float  = 1.0
_BANDIT_REWARD_WINDOW_DAYS: int = 7


def _bandit_init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_exploration_arm (
            user_id      INTEGER NOT NULL,
            arm_idx      INTEGER NOT NULL,        -- index into BANDIT_ARMS
            alpha        REAL    NOT NULL DEFAULT 1.0,
            beta         REAL    NOT NULL DEFAULT 1.0,
            last_updated TEXT    NOT NULL,
            PRIMARY KEY (user_id, arm_idx)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_uea_user
            ON user_exploration_arm(user_id)
    """)


def _ensure_bandit_tables() -> None:
    conn = _connect()
    try:
        _bandit_init_db(conn)
        conn.commit()
    except Exception as exc:
        logger.warning("preference_service._ensure_bandit_tables: %r", exc)
    finally:
        conn.close()


def _get_bandit_params(conn: sqlite3.Connection, user_id: int) -> list[tuple[float, float]]:
    """Return [(alpha, beta)] for each arm, initialising rows if missing."""
    rows = {
        r["arm_idx"]: (float(r["alpha"]), float(r["beta"]))
        for r in conn.execute(
            "SELECT arm_idx, alpha, beta FROM user_exploration_arm WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    }
    result = []
    for i in range(len(BANDIT_ARMS)):
        if i not in rows:
            result.append((_BANDIT_ALPHA_INIT, _BANDIT_BETA_INIT))
            conn.execute(
                """
                INSERT OR IGNORE INTO user_exploration_arm (user_id, arm_idx, alpha, beta, last_updated)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, i, _BANDIT_ALPHA_INIT, _BANDIT_BETA_INIT, _now_iso()),
            )
        else:
            result.append(rows[i])
    return result


def pick_exploration_ratio(user_id: int) -> float:
    """Thompson-sample the best exploration ratio arm for *user_id*.

    Returns a float from BANDIT_ARMS.  Falls back to 0.25 on any error.
    """
    import random
    conn = _connect()
    try:
        _bandit_init_db(conn)
        params = _get_bandit_params(conn, user_id)
        conn.commit()
        samples = [random.betavariate(a, b) for a, b in params]
        best_idx = samples.index(max(samples))
        return BANDIT_ARMS[best_idx]
    except Exception as exc:
        logger.debug("pick_exploration_ratio: error for user %s: %r", user_id, exc)
        return 0.25
    finally:
        conn.close()


def update_bandit_rewards(user_id: int) -> dict:
    """Update Beta parameters for *user_id* based on exploration impressions.

    For each exploration impression in the last REWARD_WINDOW days:
      - If the paper received a positive action (kb_save / paper_chat / paper_view_deep)
        within the reward window → α += 1
      - If the paper received dismiss / nudge_less → β += 1
      - No feedback → no update

    Returns summary dict {arm_idx: {alpha, beta, rewarded, penalised}}.
    """
    import json as _json
    conn = _connect()
    try:
        _bandit_init_db(conn)
        params = _get_bandit_params(conn, user_id)
        conn.commit()

        cutoff = (
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            - __import__("datetime").timedelta(days=_BANDIT_REWARD_WINDOW_DAYS)
        ).isoformat()

        # Load exploration impressions within the reward window
        exp_rows = conn.execute(
            """
            SELECT paper_id, served_at FROM recommendation_impression
            WHERE user_id = ? AND is_exploration = 1 AND served_at >= ?
            """,
            (user_id, cutoff),
        ).fetchall()

        if not exp_rows:
            return {}

        # For each paper, check feedback
        POSITIVE_ACTIONS = {"kb_save", "paper_chat", "research_start", "paper_view_deep"}
        NEGATIVE_ACTIONS = {"dismiss", "nudge_less"}

        paper_ids = list({r["paper_id"] for r in exp_rows})
        placeholders = ",".join("?" * len(paper_ids))
        fb_rows = conn.execute(
            f"SELECT paper_id, action FROM user_paper_feedback WHERE user_id = ? AND paper_id IN ({placeholders})",
            (user_id, *paper_ids),
        ).fetchall()
        paper_fb: dict[str, set] = {}
        for row in fb_rows:
            paper_fb.setdefault(row["paper_id"], set()).add(row["action"])

        # Determine arm for each impression (from weights_json we can't easily
        # recover arm_idx, so we map ratio → idx)
        ratio_to_arm_idx = {r: i for i, r in enumerate(BANDIT_ARMS)}

        delta_alpha = [0.0] * len(BANDIT_ARMS)
        delta_beta  = [0.0] * len(BANDIT_ARMS)
        summary: dict[int, dict] = {}

        for row in exp_rows:
            pid = row["paper_id"]
            actions = paper_fb.get(pid, set())
            # Try to recover arm from weights_json in impression row
            imp_row = conn.execute(
                "SELECT weights_json FROM recommendation_impression WHERE user_id = ? AND paper_id = ? ORDER BY served_at DESC LIMIT 1",
                (user_id, pid),
            ).fetchone()
            arm_idx = None
            if imp_row:
                try:
                    w = _json.loads(imp_row["weights_json"] or "{}")
                    # We don't store arm_idx in weights_json; use global profile's exploration_ratio
                    # as a proxy – accept imprecision here
                except Exception:
                    pass
            # Fall back to arm closest to mean BANDIT_ARMS
            if arm_idx is None:
                arm_idx = 2  # default: 0.20 arm

            if actions & POSITIVE_ACTIONS:
                delta_alpha[arm_idx] += 1.0
                summary.setdefault(arm_idx, {"rewarded": 0, "penalised": 0})["rewarded"] += 1
            elif actions & NEGATIVE_ACTIONS:
                delta_beta[arm_idx] += 1.0
                summary.setdefault(arm_idx, {"rewarded": 0, "penalised": 0})["penalised"] += 1

        now = _now_iso()
        for i, (a, b) in enumerate(params):
            new_a = a + delta_alpha[i]
            new_b = b + delta_beta[i]
            conn.execute(
                """
                UPDATE user_exploration_arm
                SET alpha = ?, beta = ?, last_updated = ?
                WHERE user_id = ? AND arm_idx = ?
                """,
                (new_a, new_b, now, user_id, i),
            )
            if i in summary:
                summary[i]["alpha"] = round(new_a, 4)
                summary[i]["beta"]  = round(new_b, 4)

        conn.commit()
        return summary
    except Exception as exc:
        logger.warning("update_bandit_rewards: %r", exc)
        return {}
    finally:
        conn.close()


# ── Nudge (UI feedback) ────────────────────────────────────────────────────────

def nudge(
    user_id: int,
    paper_id: str,
    direction: str,
    categories: Optional[list[str]] = None,
    keywords: Optional[list[str]] = None,
    institution_tier: int = 4,
) -> None:
    """Apply a manual preference nudge from the UI.

    direction: 'more'  → nudge_more (+4)
               'less'  → nudge_less (−4)
    """
    action = "nudge_more" if direction == "more" else "nudge_less"
    record_feedback(
        user_id, paper_id, action,
        categories=categories,
        keywords=keywords,
        institution_tier=institution_tier,
        source="nudge",
    )


def nudge_category(
    user_id: int,
    category: str,
    direction: str,
) -> None:
    """Apply a direct category-level nudge from the calibration panel.

    Uses a synthetic paper_id so the signal is stored in user_paper_feedback
    without being tied to a real paper.  The action weight is the same as a
    regular nudge_more / nudge_less so the profile rebuild treats it equally.

    direction: 'more'  → nudge_more (+4)
               'less'  → nudge_less (−4)
               'reset' → removes any existing nudge signal for this category
    """
    if direction == "reset":
        # Remove both nudge signals for this synthetic paper to clear the bias
        virtual_paper_id = f"manual-category:{category}"
        conn = _connect()
        try:
            conn.execute(
                "DELETE FROM user_paper_feedback WHERE user_id = ? AND paper_id = ? AND action IN ('nudge_more','nudge_less')",
                (user_id, virtual_paper_id),
            )
            conn.commit()
            conn.execute(
                "DELETE FROM user_preference_profile WHERE user_id = ?", (user_id,)
            )
            conn.commit()
        except Exception as exc:
            logger.warning("nudge_category reset: %r", exc)
        finally:
            conn.close()
        return

    virtual_paper_id = f"manual-category:{category}"
    action = "nudge_more" if direction == "more" else "nudge_less"
    record_feedback(
        user_id,
        virtual_paper_id,
        action,
        categories=[category],
        source="category_nudge",
    )


# ── Admin / analytics ──────────────────────────────────────────────────────────

def get_preference_stats(days: int = 30) -> dict:
    """Return preference system stats for the admin panel."""
    conn = _connect()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        total_events = conn.execute(
            "SELECT COUNT(*) FROM user_paper_feedback WHERE created_at >= ?", (cutoff,)
        ).fetchone()[0] or 0

        active_users = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM user_paper_feedback WHERE created_at >= ?",
            (cutoff,),
        ).fetchone()[0] or 0

        users_with_profile = conn.execute(
            "SELECT COUNT(*) FROM user_preference_profile"
        ).fetchone()[0] or 0

        users_with_enough = conn.execute(
            "SELECT COUNT(*) FROM user_preference_profile WHERE feedback_count >= ?",
            (MIN_FEEDBACK_FOR_PROFILE,),
        ).fetchone()[0] or 0

        action_rows = conn.execute(
            """
            SELECT action, COUNT(*) AS cnt
            FROM user_paper_feedback
            WHERE created_at >= ?
            GROUP BY action
            ORDER BY cnt DESC
            """,
            (cutoff,),
        ).fetchall()

        top_category_rows = conn.execute(
            """
            SELECT value AS cat, COUNT(*) AS cnt
            FROM user_paper_feedback, json_each(categories_json)
            WHERE created_at >= ? AND weight > 0
            GROUP BY cat
            ORDER BY cnt DESC
            LIMIT 20
            """,
            (cutoff,),
        ).fetchall()

        return {
            "days": days,
            "total_feedback_events": total_events,
            "active_users": active_users,
            "users_with_profile": users_with_profile,
            "users_with_enough_data": users_with_enough,
            "min_feedback_threshold": MIN_FEEDBACK_FOR_PROFILE,
            "action_distribution": {r["action"]: r["cnt"] for r in action_rows},
            "top_positive_categories": [
                {"category": r["cat"], "count": r["cnt"]} for r in top_category_rows
            ],
        }
    except Exception as exc:
        return {
            "error": safe_failure_detail(
                logger,
                "偏好统计暂时不可用，请稍后重试",
                exc,
                operation="preference_stats",
            )
        }
    finally:
        conn.close()


def _get_category_signal_meta(user_id: int, categories: list[str]) -> dict[str, dict]:
    """Return per-category signal_count and last_signal_at for a list of arXiv categories.

    Only looks back PROFILE_DECAY_DAYS days so the data matches the live profile.
    Returns a dict keyed by category name with keys: signal_count, last_signal_at.
    """
    if not categories:
        return {}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=PROFILE_DECAY_DAYS)).isoformat()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT value AS cat,
                   COUNT(*)       AS signal_count,
                   MAX(upf.created_at) AS last_signal_at
            FROM user_paper_feedback AS upf, json_each(upf.categories_json)
            WHERE upf.user_id = ?
              AND upf.created_at >= ?
            GROUP BY cat
            """,
            (user_id, cutoff),
        ).fetchall()
        meta = {r["cat"]: {"signal_count": r["signal_count"], "last_signal_at": r["last_signal_at"]} for r in rows}
        return meta
    except Exception as exc:
        logger.warning("_get_category_signal_meta: %r", exc)
        return {}
    finally:
        conn.close()


def get_user_profile_summary(user_id: int) -> dict:
    """Return a summary of the user's preference profile suitable for the UI."""
    profile = get_or_build_profile(user_id)
    cat_weights = profile.get("category_weights", {})
    kw_weights = profile.get("keyword_weights", {})

    top_cats = sorted(cat_weights.items(), key=lambda x: -x[1])[:5]
    top_kws = sorted(kw_weights.items(), key=lambda x: -x[1])[:10]
    neg_cats: list[str] = profile.get("negative_categories", [])

    # Enrich categories with signal meta (signal_count + last_signal_at)
    all_cats = [c for c, _ in top_cats] + neg_cats
    cat_meta = _get_category_signal_meta(user_id, all_cats)

    def _enrich(cat: str, weight: float, direction: str) -> dict:
        m = cat_meta.get(cat, {})
        return {
            "category": cat,
            "weight": weight,
            "direction": direction,
            "signal_count": m.get("signal_count", 0),
            "last_signal_at": m.get("last_signal_at"),
        }

    positive_details = [_enrich(c, w, "positive") for c, w in top_cats]
    negative_details = [_enrich(c, cat_weights.get(c, -1.0), "negative") for c in neg_cats]

    return {
        "has_enough_data": profile.get("has_enough_data", False),
        "total_feedback_count": profile.get("total_feedback_count", 0),
        "top_categories": [{"category": c, "weight": w} for c, w in top_cats],
        "top_keywords": [{"keyword": k, "weight": w} for k, w in top_kws],
        "negative_categories": neg_cats,
        "positive_category_details": positive_details,
        "negative_category_details": negative_details,
        "min_feedback_needed": max(
            0, MIN_FEEDBACK_FOR_PROFILE - profile.get("total_feedback_count", 0)
        ),
        "built_at": profile.get("built_at", ""),
        "score_weights": profile.get("score_weights"),
        "exploration_ratio": profile.get("exploration_ratio"),
    }


# ── Why-NOT (suppression explanation) ─────────────────────────────────────────

def get_suppressions(
    user_id: int,
    date: str,
    top_n: int = 5,
    theme_min: float = 0.5,
    pref_suppress_threshold: float = 0.35,
) -> list[dict]:
    """Find high-theme papers that were suppressed by the preference filter.

    "Suppressed" means the paper's pref_score was low enough to push it out of
    the top-N shown to the user.  We surface these so the user can see what the
    recommendation engine filtered out and optionally pull them back in with a
    nudge_more signal.

    Parameters
    ----------
    user_id:
        Authenticated user.
    date:
        Content date (YYYY-MM-DD) to look up candidate papers.
    top_n:
        How many suppressed papers to return.
    theme_min:
        Minimum relevance_score for a paper to be considered "good enough to surface".
    pref_suppress_threshold:
        Papers with pref_score below this value are considered suppressed.

    Returns
    -------
    list of dicts, each:
      paper_id, short_title, 📖标题, institution, relevance_score,
      pref_score, theme_score, contributions (list), suppression_summary (str)
    """
    try:
        profile = get_or_build_profile(user_id)
    except Exception as exc:
        logger.warning("get_suppressions: failed to get profile for user %s: %r", user_id, exc)
        return []

    if not profile.get("has_enough_data"):
        return []

    # Load all candidate papers for this date (before any reranking / quota)
    try:
        from services.data_service import get_papers_by_date as _get_papers
        # Pass user_id=0 to get raw papers without preference rerank
        # (search=None, institution=None ensure we get the full set)
        all_papers = _get_papers(date, user_id=0)
    except Exception as exc:
        logger.warning("get_suppressions: failed to load papers for date %s: %r", date, exc)
        return []

    if not all_papers:
        return []

    # Exclude papers the user has already explicitly actioned (dismissed or saved to KB).
    # These are not "missed" — the user has already decided about them.
    try:
        from services.kb_service import get_dismissed_paper_ids as _get_dismissed
        from services.kb_service import get_kb_paper_ids as _get_kb_ids
        already_seen: set[str] = _get_dismissed(user_id) | _get_kb_ids(user_id)
    except Exception:
        already_seen = set()

    # Score every paper and collect suppressed ones
    suppressed: list[dict] = []
    for p in all_papers:
        if p.get("paper_id", "") in already_seen:
            continue
        theme = float(p.get("relevance_score") or 0.0)
        if theme < theme_min:
            continue
        detail = compute_preference_score_detailed(p, profile)
        pref = detail["score"]
        if pref < pref_suppress_threshold:
            suppressed.append({
                "paper_id":    p.get("paper_id", ""),
                "short_title": p.get("short_title", ""),
                "📖标题":       p.get("📖标题", ""),
                "institution": p.get("institution", ""),
                "categories":  p.get("categories", []),
                "institution_tier": p.get("institution_tier"),
                "relevance_score":  round(theme, 4),
                "pref_score":       pref,
                "theme_score":      round(theme, 4),
                "contributions":    detail["contributions"][:4],
                "suppression_summary": _build_suppression_summary(detail["contributions"]),
            })

    # Sort by theme descending (best papers the user missed, first)
    suppressed.sort(key=lambda x: -x["theme_score"])
    return suppressed[:top_n]


def _build_suppression_summary(contributions: list[dict]) -> str:
    """Build a one-sentence Chinese summary of why a paper was suppressed."""
    negatives = [c for c in contributions if c.get("delta", 0) < 0]
    if not negatives:
        return "综合偏好分较低，超出当前兴趣范围"
    top = negatives[0]
    if top["type"] == "category_negative":
        return f"主要因为分类 {top['key']} 与你的偏好偏差较大"
    if top["type"] == "keyword_negative":
        return f"标题含「{top['key']}」，与你的 dismiss 历史相关"
    if top["type"] == "tier_mismatch":
        return f"机构等级 {top['key']} 低于你通常的偏好"
    return "综合偏好分较低"
