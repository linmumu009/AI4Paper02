"""
Authentication service layer.

Provides:
- User registration / credential verification
- Server-side session management
- FastAPI dependency for authenticated user
"""

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")

SESSION_COOKIE_NAME = "session_id"
SESSION_EXPIRE_DAYS = 7
SESSION_TOUCH_HOURS = 24
PBKDF2_ROUNDS = 200_000
VALID_TIERS = {"free", "pro", "pro_plus"}
VALID_ROLES = {"user", "admin", "superadmin"}
VALID_SUBSCRIPTION_TIERS = {"pro", "pro_plus"}
VALID_REDEEM_KEY_STATUS = {"active", "disabled", "consumed"}

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
_REDEEM_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_REDEEM_CODE_GROUP = 4
_REDEEM_CODE_GROUPS = 5
_REDEEM_KEY_PEPPER = os.environ.get("REDEEM_KEY_PEPPER", "CHANGE_ME_REDEEM_KEY_PEPPER")


@dataclass
class _RedeemKeyRow:
    id: int
    code_hash: str
    plan_tier: str
    duration_days: int
    max_uses: int
    used_count: int
    expire_at: Optional[str]
    status: str
    batch_id: str


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return digest.hex()


def _normalize_username(username: str) -> str:
    return (username or "").strip()


def _validate_username(username: str) -> str:
    normalized = _normalize_username(username)
    if not _USERNAME_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=400,
            detail="用户名需为 3-32 位，仅支持字母、数字、下划线、点、连字符",
        )
    return normalized


def _validate_password(password: str) -> str:
    pwd = (password or "").strip()
    if len(pwd) < 8:
        raise HTTPException(status_code=400, detail="密码长度至少 8 位")
    if len(pwd) > 128:
        raise HTTPException(status_code=400, detail="密码长度不能超过 128 位")
    return pwd


def _normalize_redeem_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def _format_redeem_code(compact_code: str) -> str:
    parts = [
        compact_code[i : i + _REDEEM_CODE_GROUP]
        for i in range(0, len(compact_code), _REDEEM_CODE_GROUP)
    ]
    return "-".join(parts)


def _generate_redeem_code() -> str:
    compact_len = _REDEEM_CODE_GROUP * _REDEEM_CODE_GROUPS
    compact = "".join(secrets.choice(_REDEEM_CODE_CHARS) for _ in range(compact_len))
    return _format_redeem_code(compact)


def _hash_redeem_code(code: str) -> str:
    normalized = _normalize_redeem_code(code)
    if not normalized:
        return ""
    return hashlib.sha256(f"{_REDEEM_KEY_PEPPER}:{normalized}".encode("utf-8")).hexdigest()


def _parse_optional_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    return _parse_iso(ts)


def _ensure_user_tier_not_expired(conn: sqlite3.Connection, user_id: int) -> None:
    row = conn.execute(
        "SELECT id, role, tier, tier_expires_at FROM auth_users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return
    role = row["role"] or "user"
    if role in ("admin", "superadmin"):
        return
    tier = (row["tier"] or "free").strip()
    expire_at = _parse_optional_iso(row["tier_expires_at"])
    if tier in VALID_SUBSCRIPTION_TIERS and expire_at and expire_at <= _now():
        now = _now_iso()
        conn.execute(
            """
            UPDATE auth_users
            SET tier = 'free', tier_expires_at = NULL, updated_at = ?
            WHERE id = ?
            """,
            (now, user_id),
        )
        conn.execute(
            """
            INSERT INTO auth_entitlements
              (user_id, source, source_ref, from_tier, to_tier, start_at, end_at, created_at, operator_user_id, note)
            VALUES (?, 'expiry', NULL, ?, 'free', ?, ?, ?, NULL, 'subscription expired')
            """,
            (user_id, tier, now, now, now),
        )


def _tier_display_label(tier: str) -> str:
    if tier == "pro_plus":
        return "Pro+"
    if tier == "pro":
        return "Pro"
    return "Free"


def init_auth_db() -> None:
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS auth_users (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                username       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                password_hash  TEXT    NOT NULL,
                salt           TEXT    NOT NULL,
                role           TEXT    NOT NULL DEFAULT 'user',
                tier           TEXT    NOT NULL DEFAULT 'free',
                tier_expires_at TEXT,
                phone          TEXT    UNIQUE,
                phone_verified INTEGER NOT NULL DEFAULT 0,
                created_at     TEXT    NOT NULL,
                updated_at     TEXT    NOT NULL,
                last_login_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS auth_sessions (
                session_id   TEXT    PRIMARY KEY,
                user_id      INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                created_at   TEXT    NOT NULL,
                expires_at   TEXT    NOT NULL,
                last_seen_at TEXT    NOT NULL,
                ip           TEXT,
                user_agent   TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at);

            CREATE TABLE IF NOT EXISTS auth_entitlements (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                source           TEXT    NOT NULL,
                source_ref       TEXT,
                from_tier        TEXT    NOT NULL,
                to_tier          TEXT    NOT NULL,
                start_at         TEXT    NOT NULL,
                end_at           TEXT,
                created_at       TEXT    NOT NULL,
                operator_user_id INTEGER,
                note             TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_auth_entitlements_user_id ON auth_entitlements(user_id);
            CREATE INDEX IF NOT EXISTS idx_auth_entitlements_created_at ON auth_entitlements(created_at);

            CREATE TABLE IF NOT EXISTS redeem_keys (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                code_hash          TEXT    NOT NULL UNIQUE,
                plan_tier          TEXT    NOT NULL,
                duration_days      INTEGER NOT NULL,
                max_uses           INTEGER NOT NULL DEFAULT 1,
                used_count         INTEGER NOT NULL DEFAULT 0,
                expire_at          TEXT,
                status             TEXT    NOT NULL DEFAULT 'active',
                batch_id           TEXT    NOT NULL,
                created_at         TEXT    NOT NULL,
                updated_at         TEXT    NOT NULL,
                created_by_user_id INTEGER,
                note               TEXT,
                last_used_at       TEXT,
                last_used_by_user_id INTEGER,
                last_used_device   TEXT,
                last_used_ip       TEXT,
                last_used_user_agent TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_redeem_keys_batch_id ON redeem_keys(batch_id);
            CREATE INDEX IF NOT EXISTS idx_redeem_keys_status ON redeem_keys(status);
            CREATE INDEX IF NOT EXISTS idx_redeem_keys_expire_at ON redeem_keys(expire_at);

            CREATE TABLE IF NOT EXISTS announcements (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                tag        TEXT    NOT NULL DEFAULT 'general',
                is_pinned  INTEGER NOT NULL DEFAULT 0,
                created_by INTEGER REFERENCES auth_users(id),
                created_at TEXT    NOT NULL,
                updated_at TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_announcements_created_at ON announcements(created_at);
            CREATE INDEX IF NOT EXISTS idx_announcements_is_pinned ON announcements(is_pinned);

            CREATE TABLE IF NOT EXISTS announcement_reads (
                user_id         INTEGER NOT NULL REFERENCES auth_users(id),
                announcement_id INTEGER NOT NULL REFERENCES announcements(id),
                read_at         TEXT    NOT NULL,
                PRIMARY KEY (user_id, announcement_id)
            );
            """
        )
        _ensure_auth_user_columns(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_auth_user_columns(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(auth_users)").fetchall()
    existing = {r["name"] for r in rows}
    if "role" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    if "tier" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN tier TEXT NOT NULL DEFAULT 'free'")
    if "tier_expires_at" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN tier_expires_at TEXT")
    if "phone" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN phone TEXT")
    if "phone_verified" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN phone_verified INTEGER NOT NULL DEFAULT 0")
    if "nickname" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN nickname TEXT DEFAULT ''")
    if "is_phone_auto_created" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN is_phone_auto_created INTEGER DEFAULT 0")
    if "is_disabled" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN is_disabled INTEGER NOT NULL DEFAULT 0")
    conn.execute("UPDATE auth_users SET role = 'user' WHERE role IS NULL OR role = ''")
    conn.execute("UPDATE auth_users SET tier = 'free' WHERE tier IS NULL OR tier = ''")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_users_phone ON auth_users(phone)")


def _cleanup_expired_sessions(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (_now_iso(),))


def _mask_phone(phone: Optional[str]) -> Optional[str]:
    """将手机号中间四位替换为 *，如 138****1234"""
    if not phone or len(phone) != 11:
        return phone
    return phone[:3] + "****" + phone[7:]


def _row_user_public(row: sqlite3.Row) -> dict:
    keys = row.keys()
    raw_phone = row["phone"] if "phone" in keys else None
    password_hash = row["password_hash"] if "password_hash" in keys else ""
    has_password = bool(password_hash and password_hash.strip())
    return {
        "id": row["id"],
        "username": row["username"],
        "nickname": row["nickname"] if "nickname" in keys else "",
        "role": row["role"],
        "tier": row["tier"],
        "tier_expires_at": row["tier_expires_at"] if "tier_expires_at" in keys else None,
        "phone": _mask_phone(raw_phone),
        "phone_verified": bool(row["phone_verified"]) if "phone_verified" in keys else False,
        "is_phone_auto_created": bool(row["is_phone_auto_created"]) if "is_phone_auto_created" in keys else False,
        "is_disabled": bool(row["is_disabled"]) if "is_disabled" in keys else False,
        "has_password": has_password,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row["last_login_at"],
    }


def _validate_phone(phone: str) -> str:
    p = (phone or "").strip()
    if not _PHONE_RE.fullmatch(p):
        raise HTTPException(status_code=400, detail="请输入有效的中国大陆手机号")
    return p


def auto_register_by_phone(phone: str) -> dict:
    """
    通过手机号自动创建账号（用于一体化登录/注册）。
    自动生成用户名，不设置密码，标记为手机号自动创建账号。
    """
    p = _validate_phone(phone)
    now = _now_iso()
    suffix = secrets.token_hex(2)
    auto_username = f"u_{p[-4:]}_{suffix}"
    conn = _connect()
    try:
        for _ in range(5):
            try:
                cur = conn.execute(
                    """
                    INSERT INTO auth_users
                      (username, password_hash, salt, phone, phone_verified,
                       nickname, is_phone_auto_created, created_at, updated_at)
                    VALUES (?, '', '', ?, 1, '', 1, ?, ?)
                    """,
                    (auto_username, p, now, now),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (cur.lastrowid,)).fetchone()
                return _row_user_public(row)
            except sqlite3.IntegrityError as exc:
                err_msg = str(exc).lower()
                if "username" in err_msg:
                    suffix = secrets.token_hex(2)
                    auto_username = f"u_{p[-4:]}_{suffix}"
                    continue
                if "phone" in err_msg or "unique" in err_msg:
                    row = conn.execute("SELECT * FROM auth_users WHERE phone = ?", (p,)).fetchone()
                    if row:
                        return _row_user_public(row)
                raise HTTPException(status_code=409, detail="自动注册失败，请稍后重试") from exc
        raise HTTPException(status_code=500, detail="自动注册失败：无法生成唯一用户名")
    finally:
        conn.close()


def register_user(username: str, password: str, phone: Optional[str] = None) -> dict:
    """
    注册用户。
    phone: 若提供则存入数据库并标记为已验证（调用方负责在注册前通过 sms_service 完成验证）。
    """
    uname = _validate_username(username)
    pwd = _validate_password(password)
    validated_phone: Optional[str] = None
    if phone:
        validated_phone = _validate_phone(phone)
    now = _now_iso()
    salt = secrets.token_bytes(16)
    pw_hash = _hash_password(pwd, salt)
    conn = _connect()
    try:
        try:
            cur = conn.execute(
                """
                INSERT INTO auth_users (username, password_hash, salt, phone, phone_verified, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (uname, pw_hash, salt.hex(), validated_phone, 1 if validated_phone else 0, now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            err_msg = str(exc).lower()
            if ("username" in err_msg or "unique" in err_msg) and "phone" not in err_msg:
                raise HTTPException(status_code=409, detail="用户名已存在") from exc
            if validated_phone and ("phone" in err_msg or "unique" in err_msg):
                raise HTTPException(status_code=409, detail="该手机号已绑定其他账号") from exc
            raise HTTPException(status_code=409, detail="用户名或手机号已存在") from exc
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_user_public(row)
    finally:
        conn.close()


def get_user_by_phone(phone: str) -> Optional[dict]:
    """按手机号查找用户，返回公开信息或 None。"""
    p = (phone or "").strip()
    if not p:
        return None
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE phone = ?", (p,)).fetchone()
        if row is None:
            return None
        return _row_user_public(row)
    finally:
        conn.close()


def login_by_phone(phone: str) -> Optional[dict]:
    """
    通过手机号登录（验证码已由调用方校验）。
    更新 last_login_at 并返回用户公开信息。
    """
    p = (phone or "").strip()
    if not p:
        return None
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE phone = ?", (p,)).fetchone()
        if row is None:
            return None
        if row["is_disabled"] if "is_disabled" in row.keys() else False:
            raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")
        _ensure_user_tier_not_expired(conn, row["id"])
        now = _now_iso()
        conn.execute(
            "UPDATE auth_users SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (now, now, row["id"]),
        )
        conn.commit()
        refreshed = conn.execute("SELECT * FROM auth_users WHERE id = ?", (row["id"],)).fetchone()
        return _row_user_public(refreshed)
    finally:
        conn.close()


def verify_credentials(username: str, password: str) -> Optional[dict]:
    uname = _normalize_username(username)
    pwd = (password or "").strip()
    if not uname or not pwd:
        return None
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE username = ?", (uname,)).fetchone()
        if row is None:
            return None
        salt = bytes.fromhex(row["salt"])
        expected = row["password_hash"]
        actual = _hash_password(pwd, salt)
        if not hmac.compare_digest(actual, expected):
            return None
        if row["is_disabled"] if "is_disabled" in row.keys() else False:
            raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")
        _ensure_user_tier_not_expired(conn, row["id"])
        now = _now_iso()
        conn.execute(
            "UPDATE auth_users SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (now, now, row["id"]),
        )
        conn.commit()
        refreshed = conn.execute("SELECT * FROM auth_users WHERE id = ?", (row["id"],)).fetchone()
        return _row_user_public(refreshed)
    finally:
        conn.close()


def create_session(
    user_id: int,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    session_id = secrets.token_urlsafe(48)
    now_dt = _now()
    now = now_dt.isoformat()
    expires = (now_dt + timedelta(days=SESSION_EXPIRE_DAYS)).isoformat()
    conn = _connect()
    try:
        _cleanup_expired_sessions(conn)
        conn.execute(
            """
            INSERT INTO auth_sessions (session_id, user_id, created_at, expires_at, last_seen_at, ip, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, user_id, now, expires, now, ip, user_agent),
        )
        conn.commit()
        return {"session_id": session_id, "expires_at": expires}
    finally:
        conn.close()


def delete_session(session_id: str) -> None:
    if not session_id:
        return
    conn = _connect()
    try:
        conn.execute("DELETE FROM auth_sessions WHERE session_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def get_user_by_session(session_id: str, touch: bool = True) -> Optional[dict]:
    if not session_id:
        return None
    conn = _connect()
    try:
        _cleanup_expired_sessions(conn)
        row = conn.execute(
            """
            SELECT s.session_id, s.expires_at, s.last_seen_at, u.*
            FROM auth_sessions s
            JOIN auth_users u ON u.id = s.user_id
            WHERE s.session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        if row["is_disabled"] if "is_disabled" in row.keys() else False:
            conn.execute("DELETE FROM auth_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return None
        _ensure_user_tier_not_expired(conn, row["id"])
        conn.commit()
        row = conn.execute(
            """
            SELECT s.session_id, s.expires_at, s.last_seen_at, u.*
            FROM auth_sessions s
            JOIN auth_users u ON u.id = s.user_id
            WHERE s.session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            return None

        expires_at = _parse_iso(row["expires_at"])
        now_dt = _now()
        if expires_at <= now_dt:
            conn.execute("DELETE FROM auth_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return None

        if touch:
            last_seen = _parse_iso(row["last_seen_at"])
            if now_dt - last_seen >= timedelta(hours=SESSION_TOUCH_HOURS):
                conn.execute(
                    "UPDATE auth_sessions SET last_seen_at = ? WHERE session_id = ?",
                    (now_dt.isoformat(), session_id),
                )
                conn.commit()

        return _row_user_public(row)
    finally:
        conn.close()


def _extract_session_id(request: Request) -> str:
    """从 Cookie 或 Authorization header 中提取 session_id。

    优先使用 Cookie（Web 同域场景）；Cookie 不存在时回退到
    ``Authorization: Bearer <session_id>``（桌面端跨域场景）。
    """
    sid = request.cookies.get(SESSION_COOKIE_NAME, "")
    if sid:
        return sid
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""


def get_current_user_optional(request: Request):
    """Return the current user dict if logged in, or None."""
    session_id = _extract_session_id(request)
    if not session_id:
        return None
    return get_user_by_session(session_id, touch=False)


def require_user(request: Request) -> dict:
    session_id = _extract_session_id(request)
    user = get_user_by_session(session_id)
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def require_admin_user(request: Request) -> dict:
    """Require admin or superadmin role."""
    user = require_user(request)
    if user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def require_superadmin_user(request: Request) -> dict:
    """Require superadmin role."""
    user = require_user(request)
    if user.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="需要超级管理员权限")
    return user


def list_users() -> list[dict]:
    conn = _connect()
    try:
        conn.execute("BEGIN")
        rows_for_expiry = conn.execute("SELECT id FROM auth_users").fetchall()
        for r in rows_for_expiry:
            _ensure_user_tier_not_expired(conn, r["id"])
        conn.commit()
        rows = conn.execute(
            """
            SELECT id, username, role, tier, tier_expires_at, created_at, updated_at, last_login_at
            FROM auth_users
            ORDER BY created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_user_tier(user_id: int, tier: str, duration_days: int = 30) -> Optional[dict]:
    if tier not in VALID_TIERS:
        raise HTTPException(status_code=400, detail="非法 tier 值")
    conn = _connect()
    try:
        if tier == "free":
            expires_at = None
        else:
            expires_at = (_now() + timedelta(days=duration_days)).isoformat()
        conn.execute(
            "UPDATE auth_users SET tier = ?, tier_expires_at = ?, updated_at = ? WHERE id = ?",
            (tier, expires_at, _now_iso(), user_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return _row_user_public(row)
    finally:
        conn.close()


def update_user_role(user_id: int, role: str) -> Optional[dict]:
    """Update a user's role (superadmin only)."""
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="非法角色值，允许: user, admin, superadmin")
    conn = _connect()
    try:
        conn.execute(
            "UPDATE auth_users SET role = ?, updated_at = ? WHERE id = ?",
            (role, _now_iso(), user_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return _row_user_public(row)
    finally:
        conn.close()


def _compute_new_subscription_expiry(
    current_tier: str,
    current_expires_at: Optional[str],
    duration_days: int,
) -> datetime:
    now_dt = _now()
    current_exp_dt = _parse_optional_iso(current_expires_at)
    anchor = now_dt
    if current_tier in VALID_SUBSCRIPTION_TIERS and current_exp_dt and current_exp_dt > now_dt:
        anchor = current_exp_dt
    return anchor + timedelta(days=duration_days)


def _apply_subscription_tier_in_conn(
    conn: sqlite3.Connection,
    user_id: int,
    target_tier: str,
    duration_days: int,
    source: str,
    source_ref: Optional[str],
    operator_user_id: Optional[int],
    note: str,
) -> dict:
    _ensure_user_tier_not_expired(conn, user_id)
    row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    current_tier = row["tier"] or "free"
    new_exp = _compute_new_subscription_expiry(current_tier, row["tier_expires_at"], duration_days)
    now = _now_iso()
    conn.execute(
        """
        UPDATE auth_users
        SET tier = ?, tier_expires_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (target_tier, new_exp.isoformat(), now, user_id),
    )
    conn.execute(
        """
        INSERT INTO auth_entitlements
          (user_id, source, source_ref, from_tier, to_tier, start_at, end_at, created_at, operator_user_id, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            source,
            source_ref,
            current_tier,
            target_tier,
            now,
            new_exp.isoformat(),
            now,
            operator_user_id,
            note.strip()[:256] if note else "",
        ),
    )
    updated = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
    if updated is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _row_user_public(updated)


def apply_subscription_tier(
    user_id: int,
    target_tier: str,
    duration_days: int,
    source: str,
    source_ref: Optional[str] = None,
    operator_user_id: Optional[int] = None,
    note: str = "",
) -> dict:
    if target_tier not in VALID_SUBSCRIPTION_TIERS:
        raise HTTPException(status_code=400, detail="只允许开通 pro 或 pro_plus")
    if duration_days <= 0 or duration_days > 3650:
        raise HTTPException(status_code=400, detail="duration_days 必须在 1~3650")

    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        updated = _apply_subscription_tier_in_conn(
            conn=conn,
            user_id=user_id,
            target_tier=target_tier,
            duration_days=duration_days,
            source=source,
            source_ref=source_ref,
            operator_user_id=operator_user_id,
            note=note,
        )
        conn.commit()
        return updated
    finally:
        conn.close()


def get_subscription_status(user_id: int) -> dict:
    conn = _connect()
    try:
        _ensure_user_tier_not_expired(conn, user_id)
        conn.commit()
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        tier = row["tier"] or "free"
        exp = row["tier_expires_at"]
        days_left: Optional[int] = None
        if exp:
            remaining = _parse_iso(exp) - _now()
            days_left = max(0, int(remaining.total_seconds() // 86400))
        return {
            "tier": tier,
            "tier_label": _tier_display_label(tier),
            "tier_expires_at": exp,
            "days_left": days_left,
        }
    finally:
        conn.close()


def issue_redeem_keys(
    plan_tier: str,
    duration_days: int,
    key_count: int,
    valid_days: Optional[int],
    max_uses: int = 1,
    created_by_user_id: Optional[int] = None,
    note: str = "",
) -> dict:
    if plan_tier not in VALID_SUBSCRIPTION_TIERS:
        raise HTTPException(status_code=400, detail="plan_tier 仅支持 pro/pro_plus")
    if duration_days <= 0 or duration_days > 3650:
        raise HTTPException(status_code=400, detail="duration_days 必须在 1~3650")
    if key_count <= 0 or key_count > 500:
        raise HTTPException(status_code=400, detail="key_count 必须在 1~500")
    if max_uses <= 0 or max_uses > 20:
        raise HTTPException(status_code=400, detail="max_uses 必须在 1~20")
    if valid_days is not None and (valid_days <= 0 or valid_days > 3650):
        raise HTTPException(status_code=400, detail="valid_days 必须在 1~3650")

    batch_id = secrets.token_hex(8)
    now = _now()
    expire_at = (now + timedelta(days=valid_days)).isoformat() if valid_days is not None else None
    created_at = now.isoformat()
    generated_codes: list[str] = []

    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        for _ in range(key_count):
            inserted = False
            for _retry in range(16):
                code = _generate_redeem_code()
                code_hash = _hash_redeem_code(code)
                try:
                    conn.execute(
                        """
                        INSERT INTO redeem_keys
                          (code_hash, plan_tier, duration_days, max_uses, used_count, expire_at, status,
                           batch_id, created_at, updated_at, created_by_user_id, note)
                        VALUES (?, ?, ?, ?, 0, ?, 'active', ?, ?, ?, ?, ?)
                        """,
                        (
                            code_hash,
                            plan_tier,
                            duration_days,
                            max_uses,
                            expire_at,
                            batch_id,
                            created_at,
                            created_at,
                            created_by_user_id,
                            note.strip()[:256] if note else "",
                        ),
                    )
                    generated_codes.append(code)
                    inserted = True
                    break
                except sqlite3.IntegrityError:
                    continue
            if not inserted:
                raise HTTPException(status_code=500, detail="生成兑换码失败，请重试")
        conn.commit()
    finally:
        conn.close()

    return {
        "batch_id": batch_id,
        "plan_tier": plan_tier,
        "duration_days": duration_days,
        "key_count": key_count,
        "expire_at": expire_at,
        "codes": generated_codes,
    }


def _load_redeem_key_by_hash(conn: sqlite3.Connection, code_hash: str) -> Optional[_RedeemKeyRow]:
    row = conn.execute(
        """
        SELECT id, code_hash, plan_tier, duration_days, max_uses, used_count, expire_at, status, batch_id
        FROM redeem_keys
        WHERE code_hash = ?
        """,
        (code_hash,),
    ).fetchone()
    if row is None:
        return None
    return _RedeemKeyRow(
        id=row["id"],
        code_hash=row["code_hash"],
        plan_tier=row["plan_tier"],
        duration_days=row["duration_days"],
        max_uses=row["max_uses"],
        used_count=row["used_count"],
        expire_at=row["expire_at"],
        status=row["status"],
        batch_id=row["batch_id"],
    )


def redeem_subscription_key(
    user_id: int,
    code: str,
    device_id: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    normalized = _normalize_redeem_code(code)
    if len(normalized) < 8:
        raise HTTPException(status_code=400, detail="兑换码格式不正确")
    code_hash = _hash_redeem_code(normalized)
    now = _now()
    now_iso = now.isoformat()

    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        key_row = _load_redeem_key_by_hash(conn, code_hash)
        if key_row is None:
            raise HTTPException(status_code=404, detail="兑换码不存在")
        if key_row.status != "active":
            if key_row.status == "consumed":
                raise HTTPException(status_code=400, detail="兑换码已使用")
            raise HTTPException(status_code=400, detail="兑换码不可用")
        if key_row.expire_at and _parse_iso(key_row.expire_at) <= now:
            conn.execute(
                "UPDATE redeem_keys SET status = 'disabled', updated_at = ? WHERE id = ?",
                (now_iso, key_row.id),
            )
            raise HTTPException(status_code=400, detail="兑换码已过期")
        if key_row.used_count >= key_row.max_uses:
            conn.execute(
                "UPDATE redeem_keys SET status = 'consumed', updated_at = ? WHERE id = ?",
                (now_iso, key_row.id),
            )
            raise HTTPException(status_code=400, detail="兑换码已使用")

        user = _apply_subscription_tier_in_conn(
            conn=conn,
            user_id=user_id,
            target_tier=key_row.plan_tier,
            duration_days=key_row.duration_days,
            source="redeem",
            source_ref=key_row.batch_id,
            operator_user_id=None,
            note=f"redeem_key:{key_row.id}",
        )

        result = conn.execute(
            """
            UPDATE redeem_keys
            SET used_count = used_count + 1,
                status = CASE WHEN used_count + 1 >= max_uses THEN 'consumed' ELSE status END,
                updated_at = ?,
                last_used_at = ?,
                last_used_by_user_id = ?,
                last_used_device = ?,
                last_used_ip = ?,
                last_used_user_agent = ?
            WHERE id = ? AND status = 'active' AND used_count < max_uses
            """,
            (
                now_iso,
                now_iso,
                user_id,
                (device_id or "")[:128],
                (ip or "")[:64],
                (user_agent or "")[:256],
                key_row.id,
            ),
        )
        if result.rowcount != 1:
            raise HTTPException(status_code=409, detail="兑换失败，请重试")
        conn.commit()
        return {
            "user": user,
            "batch_id": key_row.batch_id,
            "plan_tier": key_row.plan_tier,
            "duration_days": key_row.duration_days,
        }
    finally:
        conn.close()


def list_redeem_keys(batch_id: Optional[str] = None, limit: int = 200) -> list[dict]:
    if limit <= 0 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit 必须在 1~1000")
    conn = _connect()
    try:
        sql = """
            SELECT id, plan_tier, duration_days, max_uses, used_count, expire_at, status,
                   batch_id, created_at, created_by_user_id, last_used_at, last_used_by_user_id
            FROM redeem_keys
        """
        params: list = []
        if batch_id:
            sql += " WHERE batch_id = ?"
            params.append(batch_id.strip())
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def disable_redeem_key(key_id: int) -> bool:
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE redeem_keys SET status = 'disabled', updated_at = ? WHERE id = ?",
            (_now_iso(), key_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_user_profile(
    user_id: int,
    nickname: Optional[str] = None,
    username: Optional[str] = None,
) -> dict:
    """
    更新用户昵称和/或用户名。
    username 若提供，必须满足格式要求且不重复。
    """
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        updates: list[str] = []
        params: list = []

        if nickname is not None:
            clean_nick = nickname.strip()[:64]
            updates.append("nickname = ?")
            params.append(clean_nick)

        if username is not None:
            new_uname = _validate_username(username)
            if new_uname.lower() != row["username"].lower():
                existing = conn.execute(
                    "SELECT id FROM auth_users WHERE username = ? AND id != ?",
                    (new_uname, user_id),
                ).fetchone()
                if existing:
                    raise HTTPException(status_code=409, detail="用户名已被占用")
            updates.append("username = ?")
            params.append(new_uname)
            if row["is_phone_auto_created"]:
                updates.append("is_phone_auto_created = 0")

        if not updates:
            return _row_user_public(row)

        now = _now_iso()
        updates.append("updated_at = ?")
        params.append(now)
        params.append(user_id)

        conn.execute(
            f"UPDATE auth_users SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        refreshed = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        return _row_user_public(refreshed)
    finally:
        conn.close()


def check_username_available(username: str, exclude_user_id: Optional[int] = None) -> dict:
    """
    检查用户名是否可用。
    返回 {"available": bool, "message": str}
    """
    if not _USERNAME_RE.match(username):
        return {"available": False, "message": "用户名格式不合法，仅支持字母/数字/._-，长度 3-32 位"}
    conn = _connect()
    try:
        if exclude_user_id is not None:
            row = conn.execute(
                "SELECT id FROM auth_users WHERE username = ? AND id != ?",
                (username, exclude_user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM auth_users WHERE username = ?",
                (username,),
            ).fetchone()
        if row:
            return {"available": False, "message": "用户名已被占用"}
        return {"available": True, "message": "用户名可用"}
    finally:
        conn.close()


def set_user_password(user_id: int, password: str) -> dict:
    """
    为手机号用户首次设置密码（当前必须无密码才能调用）。
    """
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        if row["password_hash"] and row["password_hash"].strip():
            raise HTTPException(status_code=400, detail="该账号已设置密码，请使用修改密码功能")
        pwd = _validate_password(password)
        salt = secrets.token_bytes(16)
        pw_hash = _hash_password(pwd, salt)
        now = _now_iso()
        conn.execute(
            "UPDATE auth_users SET password_hash = ?, salt = ?, updated_at = ? WHERE id = ?",
            (pw_hash, salt.hex(), now, user_id),
        )
        conn.commit()
        refreshed = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        return _row_user_public(refreshed)
    finally:
        conn.close()


def change_user_password(user_id: int, old_password: str, new_password: str) -> dict:
    """
    修改已有密码（需验证旧密码）。
    """
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        if not row["password_hash"] or not row["password_hash"].strip():
            raise HTTPException(status_code=400, detail="该账号尚未设置密码，请使用设置密码功能")
        salt = bytes.fromhex(row["salt"])
        actual = _hash_password(old_password.strip(), salt)
        if not hmac.compare_digest(actual, row["password_hash"]):
            raise HTTPException(status_code=400, detail="旧密码错误")
        new_pwd = _validate_password(new_password)
        new_salt = secrets.token_bytes(16)
        new_hash = _hash_password(new_pwd, new_salt)
        now = _now_iso()
        conn.execute(
            "UPDATE auth_users SET password_hash = ?, salt = ?, updated_at = ? WHERE id = ?",
            (new_hash, new_salt.hex(), now, user_id),
        )
        conn.commit()
        refreshed = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        return _row_user_public(refreshed)
    finally:
        conn.close()


def get_user_profile(user_id: int) -> Optional[dict]:
    """获取用户完整资料（含 has_password 等）。"""
    conn = _connect()
    try:
        _ensure_user_tier_not_expired(conn, user_id)
        conn.commit()
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return _row_user_public(row)
    finally:
        conn.close()


def get_subscription_history(user_id: int) -> list:
    """获取用户的订阅记录（来自 auth_entitlements）。"""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, source, source_ref, from_tier, to_tier,
                   start_at, end_at, created_at, note
            FROM auth_entitlements
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_admin_user_detail(user_id: int) -> Optional[dict]:
    """获取指定用户的完整详情，供管理员查看。

    返回:
        {
            "user": { ...全量用户信息, 含 phone/nickname/has_password... },
            "active_sessions": int,
            "subscription_history": [ ...最近 50 条订阅变更... ]
        }
        若用户不存在则返回 None。
    """
    conn = _connect()
    try:
        _ensure_user_tier_not_expired(conn, user_id)
        conn.commit()

        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None

        user_data = _row_user_public(row)

        now = _now_iso()
        active_count = conn.execute(
            "SELECT COUNT(*) FROM auth_sessions WHERE user_id = ? AND expires_at > ?",
            (user_id, now),
        ).fetchone()[0]

        history_rows = conn.execute(
            """
            SELECT id, source, source_ref, from_tier, to_tier,
                   start_at, end_at, created_at, note
            FROM auth_entitlements
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (user_id,),
        ).fetchall()
        subscription_history = [dict(r) for r in history_rows]

        return {
            "user": user_data,
            "active_sessions": active_count,
            "subscription_history": subscription_history,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Admin user management operations
# ---------------------------------------------------------------------------

def admin_reset_password(user_id: int, new_password: str) -> dict:
    """管理员重置指定用户密码（无需旧密码）。"""
    pwd = _validate_password(new_password)
    conn = _connect()
    try:
        row = conn.execute("SELECT id FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        salt = secrets.token_bytes(16)
        pw_hash = _hash_password(pwd, salt)
        now = _now_iso()
        conn.execute(
            "UPDATE auth_users SET password_hash = ?, salt = ?, updated_at = ? WHERE id = ?",
            (pw_hash, salt.hex(), now, user_id),
        )
        conn.commit()
        refreshed = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        return _row_user_public(refreshed)
    finally:
        conn.close()


def admin_force_logout(user_id: int) -> int:
    """删除指定用户的所有活跃会话，返回被删除的会话数量。"""
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def admin_disable_user(user_id: int, operator_id: int) -> dict:
    """禁用账号：设置 is_disabled=1 并删除该用户所有会话。"""
    if user_id == operator_id:
        raise HTTPException(status_code=400, detail="不能禁用自己的账号")
    conn = _connect()
    try:
        row = conn.execute("SELECT id FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        now = _now_iso()
        conn.execute(
            "UPDATE auth_users SET is_disabled = 1, updated_at = ? WHERE id = ?",
            (now, user_id),
        )
        conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
        conn.commit()
        refreshed = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        return _row_user_public(refreshed)
    finally:
        conn.close()


def admin_enable_user(user_id: int) -> dict:
    """启用账号：清除 is_disabled 标记。"""
    conn = _connect()
    try:
        row = conn.execute("SELECT id FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        now = _now_iso()
        conn.execute(
            "UPDATE auth_users SET is_disabled = 0, updated_at = ? WHERE id = ?",
            (now, user_id),
        )
        conn.commit()
        refreshed = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        return _row_user_public(refreshed)
    finally:
        conn.close()


def admin_delete_user(user_id: int, operator_id: int) -> None:
    """永久删除用户账号及直接级联数据（auth_sessions、auth_entitlements）。
    announcements.created_by 置空（保留公告内容），announcement_reads 行直接删除。
    其他业务表的 user_id 数据因无外键约束，保留以免破坏历史记录。
    """
    if user_id == operator_id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    conn = _connect()
    try:
        row = conn.execute("SELECT id FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        conn.execute("DELETE FROM announcement_reads WHERE user_id = ?", (user_id,))
        conn.execute("UPDATE announcements SET created_by = NULL WHERE created_by = ?", (user_id,))
        conn.execute("DELETE FROM auth_users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


# Ensure tables exist on import
init_auth_db()
