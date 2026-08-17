"""Resource availability checks for recommendation and knowledge-base papers."""

from __future__ import annotations

import os
import re

from services import kb_service, translate_service


_ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$", re.IGNORECASE)


def is_recoverable_arxiv_id(paper_id: str) -> bool:
    """Return whether *paper_id* can be safely fetched from arXiv."""
    return bool(_ARXIV_ID_RE.fullmatch(str(paper_id or "").strip()))


def get_resource_status(user_id: int, paper_id: str, scope: str = "kb") -> dict:
    """Describe durable and shared resources available for one paper.

    Shared recommendation caches can expire, while copies under ``kb_files``
    are user-owned and must remain available.  Reporting both here lets the UI
    distinguish a genuine cache expiry from a broken link.
    """
    shared_pdf = kb_service._find_pdf_in_file_collect(paper_id) is not None
    shared_mineru = kb_service._find_mineru_in_file_collect(paper_id) is not None

    private_pdf = kb_service.get_kb_pdf_path(user_id, paper_id) is not None
    private_mineru = False
    try:
        paths = translate_service.kb_paper_derivative_paths(user_id, paper_id)
        private_mineru = os.path.isfile(paths["mineru"]) or os.path.isfile(
            paths["mineru_normalized"]
        )
    except (OSError, ValueError):
        private_mineru = False

    pdf_available = shared_pdf or private_pdf
    mineru_available = shared_mineru or private_mineru
    saved_paper = kb_service.get_kb_paper(user_id, paper_id, scope=scope)
    saved_to_kb = saved_paper is not None
    # An existing PDF can always be re-parsed, even for a non-arXiv item. A
    # missing PDF can only be recovered automatically from a validated arXiv
    # identifier.
    recoverable = pdf_available or is_recoverable_arxiv_id(paper_id)

    if pdf_available and mineru_available:
        state = "ready"
        message = "本地 PDF 与 MinerU 解析均可用"
        action = "none"
    elif pdf_available:
        state = "partial"
        message = "MinerU 解析缓存已过期，PDF 仍可查看"
        action = "reprocess" if saved_to_kb else "save_and_reprocess"
    elif mineru_available:
        state = "partial"
        message = "本地 PDF 缓存已过期，MinerU 解析仍可查看"
        action = "reprocess" if saved_to_kb else "save_and_reprocess"
    else:
        state = "expired"
        message = "本地 PDF 与 MinerU 解析缓存均已过期"
        action = "reprocess" if saved_to_kb else "save_and_reprocess"

    if (
        saved_paper
        and state != "ready"
        and saved_paper.get("process_status") in {"pending", "processing"}
    ):
        state = "recovering"
        action = "reprocess"
        message = "正在重新获取 PDF 并生成 MinerU 解析"
    elif not recoverable:
        action = "none"

    return {
        "paper_id": paper_id,
        "scope": scope,
        "state": state,
        "local_pdf_available": pdf_available,
        "mineru_available": mineru_available,
        "saved_to_kb": saved_to_kb,
        "recoverable": recoverable,
        "action": action,
        "message": message,
    }
