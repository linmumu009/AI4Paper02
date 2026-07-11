"""Research project (课题空间) service.

Projects upgrade the existing top-level ``kb_folders(scope='research')``
without copying or moving research output.  A project owns one legacy folder,
deep-research sessions have an optional primary ``project_id``, and other
research assets are connected through a typed relation table.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")
_RESEARCH_SCOPE = "research"
_ALLOWED_ASSET_TYPES = {"paper", "note", "compare_result", "idea"}


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def init_db() -> None:
    """Create project tables and run the idempotent legacy-folder migration."""
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_projects (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL,
                legacy_folder_id INTEGER NOT NULL,
                name             TEXT    NOT NULL,
                objective        TEXT    NOT NULL DEFAULT '',
                description      TEXT    NOT NULL DEFAULT '',
                status           TEXT    NOT NULL DEFAULT 'active',
                created_at       TEXT    NOT NULL,
                updated_at       TEXT    NOT NULL,
                archived_at      TEXT,
                UNIQUE(user_id, legacy_folder_id)
            );

            CREATE INDEX IF NOT EXISTS idx_research_projects_user_status
                ON research_projects(user_id, status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS research_project_assets (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id    INTEGER NOT NULL
                              REFERENCES research_projects(id) ON DELETE CASCADE,
                user_id       INTEGER NOT NULL,
                asset_type    TEXT    NOT NULL,
                asset_id      TEXT    NOT NULL,
                source_scope  TEXT    NOT NULL DEFAULT '',
                metadata_json TEXT    NOT NULL DEFAULT '{}',
                added_at      TEXT    NOT NULL,
                UNIQUE(project_id, asset_type, source_scope, asset_id)
            );

            CREATE INDEX IF NOT EXISTS idx_research_project_assets_project
                ON research_project_assets(project_id, added_at DESC);
            CREATE INDEX IF NOT EXISTS idx_research_project_assets_owner
                ON research_project_assets(user_id, asset_type, asset_id);
            """
        )

        if _table_exists(conn, "research_sessions") and not _column_exists(
            conn, "research_sessions", "project_id"
        ):
            conn.execute(
                "ALTER TABLE research_sessions ADD COLUMN project_id INTEGER DEFAULT NULL"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_sessions_project "
                "ON research_sessions(user_id, project_id, updated_at DESC)"
            )

        _migrate_legacy_research_folders(conn)
        conn.commit()
    finally:
        conn.close()


def _top_level_folder_id(
    conn: sqlite3.Connection,
    user_id: int,
    folder_id: int,
) -> Optional[int]:
    """Return the top-level research-folder ancestor, rejecting foreign folders."""
    current: Optional[int] = folder_id
    visited: set[int] = set()
    while current is not None and current not in visited:
        visited.add(current)
        row = conn.execute(
            "SELECT id, parent_id FROM kb_folders "
            "WHERE id=? AND user_id=? AND scope=?",
            (current, user_id, _RESEARCH_SCOPE),
        ).fetchone()
        if row is None:
            return None
        if row["parent_id"] is None:
            return int(row["id"])
        current = int(row["parent_id"])
    return None


def _migrate_legacy_research_folders(conn: sqlite3.Connection) -> None:
    """Promote top-level research folders and connect their existing sessions."""
    if not _table_exists(conn, "kb_folders"):
        return

    now = _now_iso()
    roots = conn.execute(
        "SELECT id, user_id, name, created_at, updated_at FROM kb_folders "
        "WHERE scope=? AND parent_id IS NULL",
        (_RESEARCH_SCOPE,),
    ).fetchall()
    for row in roots:
        conn.execute(
            "INSERT OR IGNORE INTO research_projects "
            "(user_id, legacy_folder_id, name, objective, description, status, "
            " created_at, updated_at) VALUES (?, ?, ?, '', '', 'active', ?, ?)",
            (
                row["user_id"],
                row["id"],
                row["name"],
                row["created_at"] or now,
                row["updated_at"] or now,
            ),
        )

    if not _column_exists(conn, "research_sessions", "project_id"):
        return
    sessions = conn.execute(
        "SELECT id, user_id, folder_id FROM research_sessions "
        "WHERE folder_id IS NOT NULL AND project_id IS NULL"
    ).fetchall()
    for session in sessions:
        root_id = _top_level_folder_id(
            conn, int(session["user_id"]), int(session["folder_id"])
        )
        if root_id is None:
            continue
        project = conn.execute(
            "SELECT id FROM research_projects "
            "WHERE user_id=? AND legacy_folder_id=? AND status!='deleted'",
            (session["user_id"], root_id),
        ).fetchone()
        if project:
            conn.execute(
                "UPDATE research_sessions SET project_id=? WHERE id=? AND user_id=?",
                (project["id"], session["id"], session["user_id"]),
            )


def _project_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "legacy_folder_id": int(row["legacy_folder_id"]),
        "name": row["name"],
        "objective": row["objective"] or "",
        "description": row["description"] or "",
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "archived_at": row["archived_at"],
    }


def _get_project_row(
    conn: sqlite3.Connection,
    user_id: int,
    project_id: int,
    *,
    include_deleted: bool = False,
) -> Optional[sqlite3.Row]:
    suffix = "" if include_deleted else " AND status!='deleted'"
    return conn.execute(
        f"SELECT * FROM research_projects WHERE id=? AND user_id=?{suffix}",
        (project_id, user_id),
    ).fetchone()


def create_project(
    user_id: int,
    name: str,
    objective: str = "",
    description: str = "",
) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValueError("课题名称不能为空")
    now = _now_iso()
    conn = _connect()
    try:
        with conn:
            folder_cur = conn.execute(
                "INSERT INTO kb_folders "
                "(user_id, scope, name, parent_id, created_at, updated_at) "
                "VALUES (?, ?, ?, NULL, ?, ?)",
                (user_id, _RESEARCH_SCOPE, name, now, now),
            )
            cur = conn.execute(
                "INSERT INTO research_projects "
                "(user_id, legacy_folder_id, name, objective, description, status, "
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
                (
                    user_id,
                    folder_cur.lastrowid,
                    name,
                    objective.strip(),
                    description.strip(),
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM research_projects WHERE id=?", (cur.lastrowid,)
            ).fetchone()
        return _project_row(row)
    finally:
        conn.close()


def list_projects(user_id: int, include_archived: bool = False) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        where = "user_id=? AND status!='deleted'"
        params: list[Any] = [user_id]
        if not include_archived:
            where += " AND status='active'"
        rows = conn.execute(
            f"SELECT * FROM research_projects WHERE {where} ORDER BY updated_at DESC",
            params,
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            project = _project_row(row)
            asset_rows = conn.execute(
                "SELECT asset_type, COUNT(*) AS count FROM research_project_assets "
                "WHERE project_id=? AND user_id=? GROUP BY asset_type",
                (row["id"], user_id),
            ).fetchall()
            counts = {asset["asset_type"]: int(asset["count"]) for asset in asset_rows}
            research_count = conn.execute(
                "SELECT COUNT(*) AS count FROM research_sessions "
                "WHERE user_id=? AND project_id=?",
                (user_id, row["id"]),
            ).fetchone()["count"]
            counts["research_session"] = int(research_count)
            project["counts"] = counts
            project["asset_count"] = sum(counts.values())
            result.append(project)
        return result
    finally:
        conn.close()


def update_project(
    user_id: int,
    project_id: int,
    *,
    name: Optional[str] = None,
    objective: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    conn = _connect()
    try:
        row = _get_project_row(conn, user_id, project_id)
        if row is None:
            return None
        updates: list[str] = []
        params: list[Any] = []
        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("课题名称不能为空")
            updates.append("name=?")
            params.append(clean_name)
        if objective is not None:
            updates.append("objective=?")
            params.append(objective.strip())
        if description is not None:
            updates.append("description=?")
            params.append(description.strip())
        if not updates:
            return _project_row(row)
        now = _now_iso()
        updates.append("updated_at=?")
        params.append(now)
        with conn:
            conn.execute(
                f"UPDATE research_projects SET {', '.join(updates)} "
                "WHERE id=? AND user_id=?",
                [*params, project_id, user_id],
            )
            if name is not None:
                conn.execute(
                    "UPDATE kb_folders SET name=?, updated_at=? "
                    "WHERE id=? AND user_id=? AND scope=?",
                    (name.strip(), now, row["legacy_folder_id"], user_id, _RESEARCH_SCOPE),
                )
        updated = _get_project_row(conn, user_id, project_id)
        return _project_row(updated) if updated else None
    finally:
        conn.close()


def set_project_status(user_id: int, project_id: int, status: str) -> bool:
    if status not in {"active", "archived", "deleted"}:
        raise ValueError("无效的课题状态")
    now = _now_iso()
    conn = _connect()
    try:
        archived_at = now if status == "archived" else None
        cur = conn.execute(
            "UPDATE research_projects SET status=?, archived_at=?, updated_at=? "
            "WHERE id=? AND user_id=? AND status!='deleted'",
            (status, archived_at, now, project_id, user_id),
        )
        if status == "deleted" and cur.rowcount:
            conn.execute(
                "DELETE FROM research_project_assets WHERE project_id=? AND user_id=?",
                (project_id, user_id),
            )
            conn.execute(
                "UPDATE research_sessions SET project_id=NULL, updated_at=? "
                "WHERE user_id=? AND project_id=?",
                (now, user_id, project_id),
            )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def project_exists(user_id: int, project_id: int, *, active_only: bool = False) -> bool:
    conn = _connect()
    try:
        row = _get_project_row(conn, user_id, project_id)
        return row is not None and (not active_only or row["status"] == "active")
    finally:
        conn.close()


def project_id_for_folder(user_id: int, folder_id: Optional[int]) -> Optional[int]:
    """Resolve any nested research folder to its owning top-level project."""
    if folder_id is None:
        return None
    conn = _connect()
    try:
        root_id = _top_level_folder_id(conn, user_id, folder_id)
        if root_id is None:
            return None
        row = conn.execute(
            "SELECT id FROM research_projects "
            "WHERE user_id=? AND legacy_folder_id=? AND status!='deleted'",
            (user_id, root_id),
        ).fetchone()
        return int(row["id"]) if row else None
    finally:
        conn.close()


def _validate_asset_owner(
    conn: sqlite3.Connection,
    user_id: int,
    asset_type: str,
    asset_id: str,
    source_scope: str,
) -> None:
    if asset_type not in _ALLOWED_ASSET_TYPES:
        raise ValueError("不支持的研究资产类型")

    row = None
    if asset_type == "paper" and source_scope == "mypapers":
        from services import user_paper_service

        if user_paper_service.get_paper(user_id, asset_id) is None:
            raise LookupError("论文不存在或无权访问")
        return
    if asset_type == "paper":
        scope = source_scope or "kb"
        row = conn.execute(
            "SELECT 1 FROM kb_papers WHERE user_id=? AND paper_id=? AND scope=?",
            (user_id, asset_id, scope),
        ).fetchone()
        if row is None and scope == "kb":
            from services import data_service

            if data_service.get_paper_detail(asset_id, user_id=user_id) is not None:
                return
    elif asset_type == "note":
        row = conn.execute(
            "SELECT 1 FROM kb_notes WHERE user_id=? AND id=?",
            (user_id, int(asset_id)),
        ).fetchone()
    elif asset_type == "compare_result":
        row = conn.execute(
            "SELECT 1 FROM kb_compare_results WHERE user_id=? AND id=?",
            (user_id, int(asset_id)),
        ).fetchone()
    elif asset_type == "idea":
        row = conn.execute(
            "SELECT 1 FROM idea_candidates WHERE user_id=? AND id=?",
            (user_id, int(asset_id)),
        ).fetchone()
    if row is None:
        raise LookupError("研究资产不存在或无权访问")


def add_asset(
    user_id: int,
    project_id: int,
    asset_type: str,
    asset_id: str,
    source_scope: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    asset_type = asset_type.strip()
    asset_id = str(asset_id).strip()
    source_scope = source_scope.strip()
    if not asset_id:
        raise ValueError("研究资产 ID 不能为空")
    conn = _connect()
    try:
        project = _get_project_row(conn, user_id, project_id)
        if project is None:
            raise LookupError("课题不存在或无权访问")
        if project["status"] != "active":
            raise ValueError("归档课题不能添加研究资产")
        _validate_asset_owner(conn, user_id, asset_type, asset_id, source_scope)
        now = _now_iso()
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO research_project_assets "
                "(project_id, user_id, asset_type, asset_id, source_scope, metadata_json, added_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    user_id,
                    asset_type,
                    asset_id,
                    source_scope,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                ),
            )
            conn.execute(
                "UPDATE research_projects SET updated_at=? WHERE id=? AND user_id=?",
                (now, project_id, user_id),
            )
        row = conn.execute(
            "SELECT * FROM research_project_assets WHERE project_id=? AND asset_type=? "
            "AND asset_id=? AND source_scope=?",
            (project_id, asset_type, asset_id, source_scope),
        ).fetchone()
        return _asset_relation_row(row)
    finally:
        conn.close()


def remove_asset(
    user_id: int,
    project_id: int,
    asset_type: str,
    asset_id: str,
    source_scope: str = "",
) -> bool:
    conn = _connect()
    try:
        if _get_project_row(conn, user_id, project_id) is None:
            return False
        cur = conn.execute(
            "DELETE FROM research_project_assets WHERE project_id=? AND user_id=? "
            "AND asset_type=? AND asset_id=? AND source_scope=?",
            (project_id, user_id, asset_type, str(asset_id), source_scope),
        )
        if cur.rowcount:
            conn.execute(
                "UPDATE research_projects SET updated_at=? WHERE id=? AND user_id=?",
                (_now_iso(), project_id, user_id),
            )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _asset_relation_row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        metadata = json.loads(row["metadata_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    return {
        "id": int(row["id"]),
        "project_id": int(row["project_id"]),
        "asset_type": row["asset_type"],
        "asset_id": row["asset_id"],
        "source_scope": row["source_scope"],
        "metadata": metadata,
        "added_at": row["added_at"],
    }


def _paper_title(data: dict[str, Any], fallback: str) -> str:
    return str(
        data.get("short_title")
        or data.get("title")
        or data.get("📖标题")
        or data.get("英文标题")
        or fallback
    )


def _resolve_asset(conn: sqlite3.Connection, user_id: int, relation: sqlite3.Row) -> dict[str, Any]:
    base = _asset_relation_row(relation)
    asset_type = base["asset_type"]
    asset_id = base["asset_id"]
    scope = base["source_scope"]
    title = asset_id
    subtitle = ""
    route = ""
    missing = False

    if asset_type == "paper" and scope == "mypapers":
        from services import user_paper_service

        paper = user_paper_service.get_paper(user_id, asset_id)
        if paper:
            title = paper.get("title") or asset_id
            subtitle = "我的论文"
            route = f"/?tab=mypapers&paper={asset_id}"
        else:
            missing = True
    elif asset_type == "paper":
        row = conn.execute(
            "SELECT paper_data FROM kb_papers WHERE user_id=? AND paper_id=? AND scope=?",
            (user_id, asset_id, scope or "kb"),
        ).fetchone()
        if row:
            try:
                data = json.loads(row["paper_data"] or "{}")
            except json.JSONDecodeError:
                data = {}
            title = _paper_title(data, asset_id)
            subtitle = asset_id
            route = f"/papers/{asset_id}"
        else:
            from services import data_service

            detail = data_service.get_paper_detail(asset_id, user_id=user_id)
            if detail:
                summary = detail.get("summary") or {}
                title = _paper_title(summary, asset_id)
                subtitle = asset_id
                route = f"/papers/{asset_id}"
            else:
                missing = True
    elif asset_type == "note":
        row = conn.execute(
            "SELECT title, paper_id FROM kb_notes WHERE user_id=? AND id=?",
            (user_id, int(asset_id)),
        ).fetchone()
        if row:
            title = row["title"] or f"笔记 {asset_id}"
            subtitle = row["paper_id"]
            route = f"/notes/{asset_id}"
        else:
            missing = True
    elif asset_type == "compare_result":
        row = conn.execute(
            "SELECT title FROM kb_compare_results WHERE user_id=? AND id=?",
            (user_id, int(asset_id)),
        ).fetchone()
        if row:
            title = row["title"] or f"对比报告 {asset_id}"
            subtitle = "论文对比"
            route = f"/?tool=compare-library&result={asset_id}"
        else:
            missing = True
    elif asset_type == "idea":
        row = conn.execute(
            "SELECT title, status FROM idea_candidates WHERE user_id=? AND id=?",
            (user_id, int(asset_id)),
        ).fetchone()
        if row:
            title = row["title"] or f"研究灵感 {asset_id}"
            subtitle = row["status"] or "研究灵感"
            route = f"/workbench?candidate_id={asset_id}"
        else:
            missing = True

    return {
        **base,
        "title": title,
        "subtitle": subtitle,
        "route": route,
        "missing": missing,
    }


def get_project(user_id: int, project_id: int) -> Optional[dict[str, Any]]:
    conn = _connect()
    try:
        row = _get_project_row(conn, user_id, project_id)
        if row is None:
            return None
        project = _project_row(row)
        relation_rows = conn.execute(
            "SELECT * FROM research_project_assets WHERE project_id=? AND user_id=? "
            "ORDER BY added_at DESC",
            (project_id, user_id),
        ).fetchall()
        assets = [_resolve_asset(conn, user_id, relation) for relation in relation_rows]
        session_rows = conn.execute(
            "SELECT id, question, paper_ids_json, config_json, parent_session_id, "
            "status, saved, folder_id, project_id, created_at, updated_at "
            "FROM research_sessions WHERE user_id=? AND project_id=? "
            "ORDER BY updated_at DESC",
            (user_id, project_id),
        ).fetchall()
        sessions: list[dict[str, Any]] = []
        for session in session_rows:
            item = dict(session)
            item["paper_ids"] = json.loads(item.pop("paper_ids_json", "[]"))
            item["config"] = json.loads(item.pop("config_json", "{}"))
            item["saved"] = bool(item.get("saved", 0))
            item["route"] = f"/?tool=research-library&session={item['id']}"
            sessions.append(item)

        counts: dict[str, int] = {"research_session": len(sessions)}
        for asset in assets:
            counts[asset["asset_type"]] = counts.get(asset["asset_type"], 0) + 1
        project["assets"] = assets
        project["sessions"] = sessions
        project["counts"] = counts
        project["asset_count"] = sum(counts.values())
        project["paper_ids"] = [
            asset["asset_id"]
            for asset in assets
            if asset["asset_type"] == "paper" and not asset["missing"]
        ]
        return project
    finally:
        conn.close()
