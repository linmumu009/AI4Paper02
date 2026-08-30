"""Reliable single-paper arXiv metadata lookup through the official OAI API."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET

import requests

from config.config import ARXIV_429_BASE_WAIT, ARXIV_429_MAX_WAIT
from Controller.http_session import build_arxiv_api_session
from services.arxiv_rate_limit import (
    RateLimitExhausted,
    compute_429_wait,
    parse_retry_after,
    wait_before_request,
)


_OAI_URL = "https://oaipmh.arxiv.org/oai"
_OAI_NAMESPACE = "http://www.openarchives.org/OAI/2.0/"
_ARXIV_NAMESPACE = "http://arxiv.org/OAI/arXiv/"


class ArxivMetadataLookupError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _child_text(element, namespace: str, name: str) -> str:
    child = element.find(f"{{{namespace}}}{name}")
    return _normalize_text(child.text if child is not None else "")


def _request_oai_record(session: requests.Session, lookup_id: str) -> bytes:
    params = {
        "verb": "GetRecord",
        "identifier": f"oai:arXiv.org:{lookup_id}",
        "metadataPrefix": "arXiv",
    }
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            wait_before_request()
            response = session.get(_OAI_URL, params=params, timeout=60)
            response.raise_for_status()
            ET.fromstring(response.content)
            return response.content
        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            status = exc.response.status_code if exc.response is not None else None
            if status != 429:
                if attempt < 3:
                    time.sleep(2 ** (attempt - 1))
                continue
            if attempt >= 3:
                raise RateLimitExhausted(
                    "arXiv OAI rate limit (429) after 3 attempts"
                ) from exc
            retry_after = (
                parse_retry_after(exc.response.headers.get("Retry-After"))
                if exc.response is not None
                else None
            )
            time.sleep(
                compute_429_wait(
                    attempt,
                    retry_after,
                    base_wait=ARXIV_429_BASE_WAIT,
                    max_wait=ARXIV_429_MAX_WAIT,
                )
            )
        except Exception as exc:
            last_exc = exc
            if attempt < 3:
                time.sleep(2 ** (attempt - 1))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("arXiv OAI request ended without a response")


def _parse_oai_record(payload: bytes | str) -> dict | None:
    root = ET.fromstring(payload)
    for error in root.findall(f"{{{_OAI_NAMESPACE}}}error"):
        code = (error.attrib.get("code") or "").strip()
        if code == "idDoesNotExist":
            return None
        raise ValueError(f"arXiv OAI error: {code or 'unknown'}")

    record = root.find(f".//{{{_OAI_NAMESPACE}}}record")
    if record is None:
        return None
    metadata = record.find(f"{{{_OAI_NAMESPACE}}}metadata")
    if metadata is None:
        return None
    arxiv = metadata.find(f"{{{_ARXIV_NAMESPACE}}}arXiv")
    if arxiv is None:
        return None

    authors: list[str] = []
    affiliations: list[str] = []
    authors_node = arxiv.find(f"{{{_ARXIV_NAMESPACE}}}authors")
    if authors_node is not None:
        for author in authors_node.findall(f"{{{_ARXIV_NAMESPACE}}}author"):
            name = _normalize_text(
                " ".join(
                    part
                    for part in (
                        _child_text(author, _ARXIV_NAMESPACE, "forenames"),
                        _child_text(author, _ARXIV_NAMESPACE, "keyname"),
                        _child_text(author, _ARXIV_NAMESPACE, "suffix"),
                    )
                    if part
                )
            )
            if name:
                authors.append(name)
            for affiliation in author.findall(f"{{{_ARXIV_NAMESPACE}}}affiliation"):
                value = _normalize_text(affiliation.text or "")
                if value and value not in affiliations:
                    affiliations.append(value)

    return {
        "title": _child_text(arxiv, _ARXIV_NAMESPACE, "title"),
        "authors": authors,
        "abstract": _child_text(arxiv, _ARXIV_NAMESPACE, "abstract"),
        "institution": affiliations[0] if affiliations else "",
        "created": _child_text(arxiv, _ARXIV_NAMESPACE, "created"),
    }


def fetch_arxiv_metadata(arxiv_id: str) -> dict:
    """Return metadata for one already-normalized ID without the export API."""
    clean_id = str(arxiv_id or "").strip()
    if not clean_id:
        raise ArxivMetadataLookupError("arXiv ID 不能为空", status_code=400)
    lookup_id = re.sub(r"v\d+$", "", clean_id, flags=re.IGNORECASE)
    try:
        with build_arxiv_api_session() as session:
            parsed = _parse_oai_record(_request_oai_record(session, lookup_id))
    except RateLimitExhausted as exc:
        raise ArxivMetadataLookupError(
            "arXiv 请求过于频繁，请稍等片刻后重试，或改用 PDF 上传方式导入。",
            status_code=503,
        ) from exc
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        raise ArxivMetadataLookupError(
            f"arXiv 服务暂时不可用（HTTP {status or 'unknown'}），请稍后重试",
            status_code=502,
        ) from exc
    except Exception as exc:
        raise ArxivMetadataLookupError(
            "arXiv 服务暂时不可用，请稍后重试",
            status_code=502,
        ) from exc

    if parsed is None:
        raise ArxivMetadataLookupError(
            f"arXiv 未找到 ID: {clean_id}",
            status_code=404,
        )

    year = None
    if re.match(r"^\d{4}", parsed["created"] or ""):
        year = int(parsed["created"][:4])
    return {
        "arxiv_id": clean_id,
        "title": parsed["title"],
        "authors": parsed["authors"],
        "abstract": parsed["abstract"],
        "institution": parsed["institution"],
        "year": year,
        "external_url": f"https://arxiv.org/abs/{clean_id}",
        "pdf_url": f"https://arxiv.org/pdf/{clean_id}",
    }
