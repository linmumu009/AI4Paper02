"""Per-User Score-Weight Calibration Script.

Searches the (W_theme, W_pref, W_novel) simplex for weights that maximise
NDCG@10 for each eligible user, then writes the best weights back into the
user's preference profile.

Usage
-----
  # Calibrate all eligible users (dry-run, prints results but writes nothing)
  python -m scripts.calibrate_user_weights --dry-run

  # Calibrate a single user (live write)
  python -m scripts.calibrate_user_weights --user-id 42

  # Calibrate all, look back 30 days, require at least 5 saves
  python -m scripts.calibrate_user_weights --days 30 --min-saves 5

  # Run from the Sever/ directory or set PYTHONPATH to include Sever/

Eligibility criteria (per plan)
--------------------------------
  >= MIN_IMPRESSIONS impressions in the last *days* days
  >= min_saves positive feedback events (kb_save, paper_chat, etc.) in that window

NDCG@10 graded relevance
--------------------------
  kb_save          → 3
  paper_chat       → 2
  research_start   → 2
  paper_view_deep  → 1
  dismiss          → -1  (treated as rel=0, excluded from DCG but used for penalty)

Weight grid
-----------
  ~200-point simplex lattice over (theme, pref, novel) where each coordinate
  is a multiple of 0.1 and they sum to 1.0.

Improvement threshold
---------------------
  If best NDCG improves over current weights by < MIN_IMPROVEMENT_PCT, no write.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from itertools import product
from typing import Optional

# ── Ensure Sever/ is on path when running as script ───────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SEVER_ROOT = os.path.dirname(_SCRIPT_DIR)
if _SEVER_ROOT not in sys.path:
    sys.path.insert(0, _SEVER_ROOT)

from services import impression_service, preference_service, calibration_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("calibrate_user_weights")

# ── Constants ─────────────────────────────────────────────────────────────────

# NDCG relevance grades: action → grade (missing = 0)
RELEVANCE_GRADES: dict[str, int] = {
    "kb_save":         3,
    "paper_chat":      2,
    "research_start":  2,
    "paper_view_deep": 1,
    # dismiss and nudge_less are treated as grade=0 (not in DCG)
}

NDCG_K: int = 10
MIN_IMPRESSIONS: int = 30
MIN_IMPROVEMENT_PCT: float = 0.05   # 5 % relative improvement required to write

# Weight grid: each coordinate steps by GRID_STEP, must sum to 1.0
GRID_STEP: float = 0.1


# ── NDCG computation ──────────────────────────────────────────────────────────

def _dcg(relevances: list[float], k: int) -> float:
    """Compute Discounted Cumulative Gain at rank k."""
    total = 0.0
    for i, rel in enumerate(relevances[:k]):
        if rel > 0:
            total += rel / math.log2(i + 2)   # log2(rank + 1), rank is 1-based
    return total


def _ndcg(ranked_relevances: list[float], k: int) -> float:
    """Compute normalised DCG at rank k."""
    dcg = _dcg(ranked_relevances, k)
    ideal = _dcg(sorted(ranked_relevances, reverse=True), k)
    if ideal == 0.0:
        return 0.0
    return dcg / ideal


# ── Weight grid ───────────────────────────────────────────────────────────────

def _build_weight_grid(step: float = GRID_STEP) -> list[tuple[float, float, float]]:
    """Return all (w_t, w_p, w_n) triples on the simplex that sum to 1.0."""
    grid = []
    n = round(1.0 / step)
    for i in range(n + 1):
        for j in range(n + 1 - i):
            k = n - i - j
            w_t = round(i * step, 4)
            w_p = round(j * step, 4)
            w_n = round(k * step, 4)
            if abs(w_t + w_p + w_n - 1.0) < 1e-6 and w_t >= 0 and w_p >= 0 and w_n >= 0:
                grid.append((w_t, w_p, w_n))
    return grid


# ── Per-user calibration ───────────────────────────────────────────────────────

def _score_paper_with_weights(
    pref_score: float,
    theme_score: float,
    novel_score: float,
    w_t: float,
    w_p: float,
    w_n: float,
) -> float:
    return w_t * theme_score + w_p * pref_score + w_n * novel_score


def calibrate_user(
    user_id: int,
    days: int = 30,
    min_saves: int = 5,
    dry_run: bool = False,
    verbose: bool = False,
) -> Optional[dict]:
    """Run calibration for one user.  Returns result dict or None if skipped."""

    # ── Load impressions ──────────────────────────────────────────────────────
    impressions = impression_service.get_impressions_for_user(user_id, days=days)
    if len(impressions) < MIN_IMPRESSIONS:
        if verbose:
            logger.info("User %d: only %d impressions (need %d) — skipping",
                        user_id, len(impressions), MIN_IMPRESSIONS)
        return None

    # ── Load feedback events ───────────────────────────────────────────────────
    import sqlite3 as _sq
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    conn = _sq.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = _sq.Row
    feedback_rows = conn.execute(
        """
        SELECT paper_id, action FROM user_paper_feedback
        WHERE user_id = ? AND created_at >= ?
        """,
        (user_id, cutoff),
    ).fetchall()
    conn.close()

    # Build paper_id → best relevance grade mapping
    paper_relevance: dict[str, int] = {}
    for row in feedback_rows:
        pid = row["paper_id"]
        grade = RELEVANCE_GRADES.get(row["action"], 0)
        if grade > paper_relevance.get(pid, 0):
            paper_relevance[pid] = grade

    n_saves = sum(1 for pid, g in paper_relevance.items() if g >= 2)
    if n_saves < min_saves:
        if verbose:
            logger.info("User %d: only %d saves (need %d) — skipping", user_id, n_saves, min_saves)
        return None

    # ── Build impression records keyed by (date_str, paper_id) ───────────────
    # Use the most recent impression per (date_str, paper_id) in case of duplicates
    best_imp: dict[tuple[str, str], dict] = {}
    for imp in impressions:
        key = (imp["date_str"], imp["paper_id"])
        existing = best_imp.get(key)
        if existing is None or imp["served_at"] > existing["served_at"]:
            best_imp[key] = imp

    imp_list = list(best_imp.values())

    # ── Build weight grid ──────────────────────────────────────────────────────
    grid = _build_weight_grid(GRID_STEP)
    if verbose:
        logger.info("User %d: %d impressions, %d saves, grid size %d",
                    user_id, len(imp_list), n_saves, len(grid))

    # ── Compute NDCG for each weight tuple ────────────────────────────────────
    def _ndcg_for_weights(w_t: float, w_p: float, w_n: float) -> float:
        """
        For each date that has >= 2 impressions, re-rank them with (w_t,w_p,w_n)
        and compute NDCG@K against the feedback grades.  Average across dates.
        """
        # Group by date_str
        by_date: dict[str, list[dict]] = {}
        for imp in imp_list:
            by_date.setdefault(imp["date_str"], []).append(imp)

        ndcg_values = []
        for date_imps in by_date.values():
            if len(date_imps) < 2:
                continue
            # Re-score and sort
            scored = sorted(
                date_imps,
                key=lambda x: -_score_paper_with_weights(
                    x.get("pref_score", 0.5),
                    x.get("theme_score", 0.5),
                    x.get("novel_score", 0.5),
                    w_t, w_p, w_n,
                ),
            )
            relevances = [float(paper_relevance.get(x["paper_id"], 0)) for x in scored]
            ndcg_values.append(_ndcg(relevances, NDCG_K))

        if not ndcg_values:
            return 0.0
        return sum(ndcg_values) / len(ndcg_values)

    # ── Get current profile weights for baseline ───────────────────────────────
    try:
        profile = preference_service.get_or_build_profile(user_id)
    except Exception as exc:
        logger.warning("User %d: failed to get profile: %r", user_id, exc)
        return None

    stored = profile.get("score_weights") or {}
    current_w = (
        float(stored.get("theme", preference_service.W_THEME)),
        float(stored.get("pref",  preference_service.W_PREF)),
        float(stored.get("novel", preference_service.W_NOVEL)),
    )
    ndcg_current = _ndcg_for_weights(*current_w)

    best_w = current_w
    best_ndcg = ndcg_current

    for w_t, w_p, w_n in grid:
        ndcg = _ndcg_for_weights(w_t, w_p, w_n)
        if ndcg > best_ndcg:
            best_ndcg = ndcg
            best_w = (w_t, w_p, w_n)

    # ── Check improvement threshold ────────────────────────────────────────────
    improvement = (best_ndcg - ndcg_current) / max(ndcg_current, 1e-9)
    result = {
        "user_id": user_id,
        "n_impressions": len(imp_list),
        "n_saves": n_saves,
        "current_weights": {"theme": current_w[0], "pref": current_w[1], "novel": current_w[2]},
        "best_weights":    {"theme": best_w[0],    "pref": best_w[1],    "novel": best_w[2]},
        "ndcg_current": round(ndcg_current, 6),
        "ndcg_best":    round(best_ndcg, 6),
        "improvement":  round(improvement, 4),
        "wrote": False,
    }

    if improvement < MIN_IMPROVEMENT_PCT:
        if verbose:
            logger.info("User %d: improvement %.1f%% < threshold %.1f%% — not updating",
                        user_id, improvement * 100, MIN_IMPROVEMENT_PCT * 100)
        return result

    # ── Write back (unless dry-run) ────────────────────────────────────────────
    if not dry_run:
        try:
            import sqlite3 as _sq2
            conn2 = _sq2.connect(_DB_PATH, check_same_thread=False)
            conn2.row_factory = _sq2.Row
            profile_row = conn2.execute(
                "SELECT profile_json FROM user_preference_profile WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if profile_row:
                p = json.loads(profile_row["profile_json"] or "{}")
                p["score_weights"] = result["best_weights"]
                from datetime import datetime as _dt, timezone as _tz
                conn2.execute(
                    "UPDATE user_preference_profile SET profile_json = ? WHERE user_id = ?",
                    (json.dumps(p, ensure_ascii=False), user_id),
                )
                conn2.commit()
            conn2.close()

            calibration_service.record_calibration(
                user_id=user_id,
                old_weights=result["current_weights"],
                new_weights=result["best_weights"],
                ndcg_old=ndcg_current,
                ndcg_new=best_ndcg,
                n_impressions=len(imp_list),
                n_saves=n_saves,
            )
            result["wrote"] = True
            logger.info(
                "User %d: wrote new weights %s (NDCG %.4f → %.4f, +%.1f%%)",
                user_id,
                result["best_weights"],
                ndcg_current, best_ndcg,
                improvement * 100,
            )
        except Exception as exc:
            logger.error("User %d: failed to write weights: %r", user_id, exc)
    else:
        logger.info(
            "User %d: [dry-run] would write %s (NDCG %.4f → %.4f, +%.1f%%)",
            user_id,
            result["best_weights"],
            ndcg_current, best_ndcg,
            improvement * 100,
        )

    return result


# ── CLI entrypoint ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibrate per-user score weights using NDCG@10 grid search."
    )
    parser.add_argument("--user-id", type=int, default=None,
                        help="Calibrate a single user. If omitted, calibrate all eligible users.")
    parser.add_argument("--days", type=int, default=30,
                        help="Lookback window in days (default: 30).")
    parser.add_argument("--min-saves", type=int, default=5,
                        help="Min positive feedback events required (default: 5).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results but do not write to DB.")
    parser.add_argument("--verbose", action="store_true",
                        help="Print per-user debug messages.")
    args = parser.parse_args()

    # Ensure calibration DB tables exist
    calibration_service.init_db()

    if args.user_id is not None:
        result = calibrate_user(
            args.user_id,
            days=args.days,
            min_saves=args.min_saves,
            dry_run=args.dry_run,
            verbose=True,
        )
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"User {args.user_id}: not eligible or skipped")
        return

    # All eligible users
    eligible = impression_service.get_unique_users_with_impressions(
        min_impressions=MIN_IMPRESSIONS, days=args.days
    )
    logger.info("Found %d user(s) with >= %d impressions in last %d days",
                len(eligible), MIN_IMPRESSIONS, args.days)

    wrote = skipped = failed = 0
    for uid in eligible:
        try:
            res = calibrate_user(
                uid,
                days=args.days,
                min_saves=args.min_saves,
                dry_run=args.dry_run,
                verbose=args.verbose,
            )
            if res is None:
                skipped += 1
            elif res["wrote"]:
                wrote += 1
            else:
                skipped += 1
        except Exception as exc:
            logger.error("User %d: unexpected error: %r", uid, exc)
            failed += 1

    logger.info("Done: %d wrote, %d skipped, %d failed", wrote, skipped, failed)


if __name__ == "__main__":
    main()
