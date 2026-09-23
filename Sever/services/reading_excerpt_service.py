"""Append reading excerpts without replacing the note's existing body."""
from html import escape
from services import kb_service


def append_excerpt(user_id: int, note_id: int, paper_id: str, scope: str,
                   text: str, source_path: str):
    conn = kb_service._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM kb_notes WHERE id = ? AND user_id = ? AND paper_id = ? AND scope = ? AND type = 'markdown'",
            (note_id, user_id, paper_id, scope),
        ).fetchone()
        if row is None:
            return None
        href = escape(source_path, quote=True)
        content = row["content"] or ""
        if href not in content:
            quote = escape(text).replace("\n", "<br>")
            attrs = f'href="{href}" target="_blank" rel="noopener noreferrer"'
            content += f'<blockquote><p><a {attrs}>{quote}</a></p></blockquote><p><a {attrs}>返回论文原文 ↗</a></p>'
            if len(content) > 500000:
                raise ValueError("笔记内容已达上限，请选择其他笔记或新建笔记。")
            conn.execute("UPDATE kb_notes SET content = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                         (content, kb_service._now_iso(), note_id, user_id))
        updated = conn.execute("SELECT * FROM kb_notes WHERE id = ? AND user_id = ?", (note_id, user_id)).fetchone()
        conn.commit()
        return kb_service._row_to_dict(updated)
    finally:
        conn.close()
