#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import logging
import json
import re
import time
import traceback
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, date, time as dtime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import List, Optional, Tuple
from urllib.parse import quote

import requests
import feedparser
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass
from config.config import (
    API_URL,
    SEARCH_CATEGORIES,
    ARXIV_USER_AGENT,
    ARXIV_429_BASE_WAIT,
    ARXIV_429_MAX_WAIT,
    OUTPUT_DIR,
    ARXIV_JSON_DIR,
    FILENAME_FMT,
    JSON_FILENAME_FMT,
    PAGE_SIZE_DEFAULT,
    MAX_PAPERS_DEFAULT,
    SLEEP_DEFAULT,
    USE_PROXY_DEFAULT,
    RETRY_COUNT,
    PROGRESS_SINGLE_LINE,
)
from Controller.http_session import build_arxiv_api_session
from services.arxiv_rate_limit import (
    ARXIV_EXIT_RATE_LIMIT_PARTIAL,
    RateLimitExhausted,
    compute_429_wait,
    parse_retry_after,
    wait_before_request,
)

try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:
    ZoneInfo = None

ARXIV_API = API_URL
ARXIV_RSS_BASE_URL = "https://export.arxiv.org/rss"
ARXIV_OAI_URL = "https://oaipmh.arxiv.org/oai"
ARXIV_EXIT_BATCH_NOT_READY = 4
_RSS_INCLUDED_ANNOUNCE_TYPES = {"new", "cross"}
_OAI_NAMESPACE = "http://www.openarchives.org/OAI/2.0/"
_ARXIV_OAI_NAMESPACE = "http://arxiv.org/OAI/arXiv/"


class AnnouncementBatchNotReady(RuntimeError):
    """The official listing has not advanced to the requested batch yet."""

    def __init__(self, requested: date, available: date, category: str):
        self.requested = requested
        self.available = available
        self.category = category
        super().__init__(
            f"official listing batch for {category} is {available.isoformat()}, "
            f"requested {requested.isoformat()}"
        )


class AnnouncementMetadataIncomplete(RuntimeError):
    """The listing was available but its paper metadata was incomplete."""


def setup_logging():
    logger = logging.getLogger("arxiv")
    logger.setLevel(logging.INFO)

    # Observability is not a business prerequisite.  Reused handlers can keep
    # stale file descriptors or duplicate output during in-process probes.
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)

    fmt = logging.Formatter("[%(levelname)s] %(message)s")

    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    try:
        project_root = os.path.dirname(os.path.dirname(__file__))
        log_root = os.path.join(project_root, "logs")
        date_dir = datetime.now().strftime("%Y-%m-%d")
        log_dir = os.path.join(log_root, date_dir)
        os.makedirs(log_dir, exist_ok=True)
        start_name = datetime.now().strftime("%H%M%S") + ".log"
        fh = logging.FileHandler(
            os.path.join(log_dir, start_name), encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter("%(asctime)s " + fmt._fmt))
        logger.addHandler(fh)
    except OSError as exc:
        logger.warning(
            "File logging unavailable (%s); continuing with stdout only.",
            type(exc).__name__,
        )

    return logger


def arxiv_id_from_entry_url(entry_id_url: str) -> str:
    value = (entry_id_url or "").strip().split("?", 1)[0].rstrip("/")
    m = re.search(r"/abs/(.+?)(?:v\d+)?$", value)
    if m:
        return m.group(1)
    oai_match = re.match(r"oai:arXiv\.org:(.+?)(?:v\d+)?$", value, re.IGNORECASE)
    return oai_match.group(1) if oai_match else value


def arxiv_id_sort_key(arxiv_id: str) -> tuple:
    """Provide a deterministic newest-first key across merged category feeds."""
    modern = re.fullmatch(r"(\d{4})\.(\d+)", (arxiv_id or "").strip())
    if modern:
        return 1, int(modern.group(1)), int(modern.group(2))
    return 0, (arxiv_id or "")


def entry_published_utc_dt(entry) -> datetime:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt_utc = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    else:
        dt_utc = datetime.fromisoformat(entry.published.replace("Z", "+00:00"))
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(timezone.utc)


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def parse_entry_authors(entry) -> List[str]:
    authors = []
    for a in getattr(entry, "authors", None) or []:
        # feedparser 里 a 可能是 dict / FeedParserDict / 对象，兼容取法
        name = ""
        if isinstance(a, dict):
            name = a.get("name", "")
        else:
            name = (
                getattr(a, "name", "")
                or (getattr(a, "get", None) and a.get("name"))
                or ""
            )
        name = normalize_text(name)
        if name:
            authors.append(name)
    return authors


def parse_entry_summary(entry) -> str:
    return normalize_text(
        getattr(entry, "summary", "") or getattr(entry, "description", "")
    )


def parse_entry_categories(entry) -> List[str]:
    """Extract arXiv category tags from a feedparser entry (e.g. ['cs.CL', 'cs.LG'])."""
    cats: List[str] = []
    for tag in getattr(entry, "tags", None) or []:
        term = ""
        if isinstance(tag, dict):
            term = tag.get("term", "")
        else:
            term = getattr(tag, "term", "") or ""
        term = term.strip()
        if term:
            cats.append(term)
    return cats


def _feed_value(container, key: str, default=""):
    if isinstance(container, dict):
        return container.get(key, default)
    value = getattr(container, key, default)
    if value != default:
        return value
    getter = getattr(container, "get", None)
    return getter(key, default) if getter else default


def parse_rss_batch_date(feed) -> date:
    """Read the announcement date encoded by an official arXiv RSS channel."""
    channel = getattr(feed, "feed", None) or {}
    raw = normalize_text(
        _feed_value(channel, "published", "")
        or _feed_value(channel, "updated", "")
    )
    if not raw:
        raise ValueError("arXiv RSS channel did not include pubDate/lastBuildDate")
    parsed = parsedate_to_datetime(raw)
    if parsed is None:
        raise ValueError(f"invalid arXiv RSS batch date: {raw!r}")
    # Keep the calendar date in the offset carried by the RSS value.  arXiv's
    # channel pubDate is midnight US Eastern time and directly names the batch.
    return parsed.date()


def parse_rss_announce_type(entry) -> str:
    value = (
        _feed_value(entry, "arxiv_announce_type", "")
        or _feed_value(entry, "announce_type", "")
    )
    if value:
        return normalize_text(str(value)).lower()

    # Some feedparser versions leave the namespace field only in description.
    description = str(
        _feed_value(entry, "summary", "")
        or _feed_value(entry, "description", "")
    )
    match = re.search(r"Announce\s+Type:\s*([\w-]+)", description, re.IGNORECASE)
    return match.group(1).lower() if match else ""


def parse_rss_summary(entry) -> str:
    summary = parse_entry_summary(entry)
    # RSS descriptions start with transport metadata that should not leak into
    # the abstract displayed to users.
    summary = re.sub(
        r"^arXiv:\S+\s+Announce\s+Type:\s*[\w-]+\s*",
        "",
        summary,
        flags=re.IGNORECASE,
    )
    summary = re.sub(r"^Abstract:\s*", "", summary, flags=re.IGNORECASE)
    return normalize_text(summary)


def parse_rss_authors(entry) -> List[str]:
    authors = parse_entry_authors(entry)
    if authors:
        expanded: List[str] = []
        for author in authors:
            expanded.extend(
                part.strip()
                for part in re.split(r"\s+and\s+|;\s*|,\s*", author)
                if part.strip()
            )
        return expanded
    raw = normalize_text(
        str(
            _feed_value(entry, "dc_creator", "")
            or _feed_value(entry, "author", "")
        )
    )
    if not raw:
        return []
    return [
        part.strip()
        for part in re.split(r"\s+and\s+|;\s*|,\s*", raw)
        if part.strip()
    ]


def paper_from_rss_entry(entry, batch_date: date) -> "Paper":
    entry_url = str(
        _feed_value(entry, "link", "")
        or _feed_value(entry, "id", "")
    )
    arxiv_id = arxiv_id_from_entry_url(entry_url)
    published_utc = datetime.combine(batch_date, dtime(0, 0), tzinfo=timezone.utc)
    try:
        published_utc = entry_published_utc_dt(entry)
    except (AttributeError, TypeError, ValueError):
        pass
    return Paper(
        title=normalize_text(str(_feed_value(entry, "title", ""))),
        published_utc=published_utc,
        arxiv_id=arxiv_id,
        link=f"https://arxiv.org/abs/{arxiv_id}",
        authors=parse_rss_authors(entry),
        summary=parse_rss_summary(entry),
        paper_categories=parse_entry_categories(entry),
    )


def _parse_utc_datetime(s: str, *, is_end: bool) -> datetime:
    s = s.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if is_end:
            dt = dt + timedelta(days=1)
        return dt

    iso = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def local_midnight_as_utc(anchor_tz: str, anchor_date: date) -> datetime:
    if ZoneInfo is None:
        raise RuntimeError("zoneinfo not available; cannot convert local midnight to UTC.")
    tz = ZoneInfo(anchor_tz)
    dt_local = datetime.combine(anchor_date, dtime(0, 0), tzinfo=tz)
    return dt_local.astimezone(timezone.utc)


def compute_window_by_midnight_anchor(
    *,
    anchor_tz: str,
    days: int,
    anchor_date_str: Optional[str],
) -> Tuple[datetime, datetime]:
    if days <= 0:
        raise ValueError("days must be positive")
    if ZoneInfo is None:
        raise RuntimeError("zoneinfo not available; cannot compute anchor-based window.")

    tz = ZoneInfo(anchor_tz)
    if anchor_date_str:
        anchor_date = date.fromisoformat(anchor_date_str)
    else:
        anchor_date = datetime.now(tz).date()

    end_utc = local_midnight_as_utc(anchor_tz, anchor_date)
    start_utc = end_utc - timedelta(days=days)
    return start_utc, end_utc


def compute_submission_window_for_announcement_date(
    announcement_date: date,
) -> Tuple[datetime, datetime]:
    """Approximate one historical batch by arXiv's 14:00 US-Eastern cutoffs.

    Current batches use RSS and do not need this approximation.  It is only a
    safer fallback for dates no longer retained by RSS: Tuesday's batch spans
    the weekend, while the other weekday batches span adjacent business-day
    cutoffs.
    """
    if announcement_date.weekday() >= 5:
        raise ValueError("arXiv announcement dates must be Monday through Friday")
    if ZoneInfo is None:
        raise RuntimeError("zoneinfo not available; cannot compute arXiv cutoff window")

    end_cutoff_date = announcement_date - timedelta(
        days=3 if announcement_date.weekday() == 0 else 1
    )
    start_cutoff_date = end_cutoff_date - timedelta(
        days=3 if end_cutoff_date.weekday() == 0 else 1
    )
    eastern = ZoneInfo("America/New_York")
    start_local = datetime.combine(start_cutoff_date, dtime(14, 0), tzinfo=eastern)
    end_local = datetime.combine(end_cutoff_date, dtime(14, 0), tzinfo=eastern)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _floor_to_minute(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    return dt.replace(second=0, microsecond=0)


def _ceil_to_minute(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    if dt.second == 0 and dt.microsecond == 0:
        return dt
    dt = dt + timedelta(minutes=1)
    return dt.replace(second=0, microsecond=0)


def _to_arxiv_minute_str(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%d%H%M")


def build_submitted_date_clause(start_utc: datetime, end_utc: datetime) -> str:
    start_s = _to_arxiv_minute_str(_floor_to_minute(start_utc))
    end_s = _to_arxiv_minute_str(_ceil_to_minute(end_utc))
    return f"submittedDate:[{start_s} TO {end_s}]"


_ARXIV_FIELD_PREFIX_RE = re.compile(
    r"\b(?:ti|au|abs|co|jr|cat|rn|all|id|submittedDate|lastUpdatedDate)\s*:",
    re.IGNORECASE,
)
_ARXIV_BOOL_OR_GROUP_RE = re.compile(r"\b(?:AND|OR|ANDNOT)\b|[()\[\]]", re.IGNORECASE)


def is_advanced_arxiv_query(q: str) -> bool:
    q = (q or "").strip()
    if not q:
        return False
    return bool(_ARXIV_FIELD_PREFIX_RE.search(q) or _ARXIV_BOOL_OR_GROUP_RE.search(q))


def semantic_query_to_all_clause(q: str) -> str:
    q = (q or "").strip()
    if not q:
        return ""

    tokens: List[Tuple[str, bool]] = []
    for m in re.finditer(r'"([^"]+)"|(\S+)', q):
        if m.group(1) is not None:
            tokens.append((m.group(1), True))
        else:
            tokens.append((m.group(2), False))

    cleaned: List[Tuple[str, bool]] = []
    for t, is_phrase in tokens:
        t = t.strip()
        if t:
            cleaned.append((t, is_phrase))

    if not cleaned:
        return ""

    parts: List[str] = []
    for t, is_phrase in cleaned:
        if is_phrase:
            parts.append(f'all:"{t}"')
        else:
            parts.append(f"all:{t}")

    return " AND ".join(parts)


def build_text_clause(user_query: str) -> str:
    user_query = (user_query or "").strip()
    if not user_query:
        return ""
    if is_advanced_arxiv_query(user_query):
        return user_query
    return semantic_query_to_all_clause(user_query)


def build_category_clause(categories: List[str]) -> str:
    cats = [c.strip() for c in (categories or []) if c.strip()]
    if not cats:
        return ""
    inner = " OR ".join([f"cat:{c}" for c in cats])
    return f"({inner})"


def build_search_query(
    *,
    categories: List[str],
    user_query: str,
    start_utc: datetime,
    end_utc: datetime,
) -> str:
    clauses: List[str] = []
    cat_clause = build_category_clause(categories)
    if cat_clause:
        clauses.append(cat_clause)
    text_clause = build_text_clause(user_query)
    if text_clause:
        clauses.append(f"({text_clause})")
    date_clause = build_submitted_date_clause(start_utc, end_utc)
    clauses.append(date_clause)
    return " AND ".join(clauses)


def fetch_page_with_retry(
    session: requests.Session,
    params: dict,
    logger,
    retries: int = 5,
    *,
    base_429_wait: float = ARXIV_429_BASE_WAIT,
    max_429_wait: float = ARXIV_429_MAX_WAIT,
):
    """Fetch one page from the arXiv API with retry/backoff.

    Returns (feed, had_rate_limit) where had_rate_limit is True if any 429
    response was received during this call.
    Raises RateLimitExhausted when all 429 retries are exhausted.
    Raises the last exception for other HTTP errors.
    """
    backoff = 1.0
    last_exc = None
    had_rate_limit = False
    for attempt in range(1, retries + 1):
        try:
            wait_before_request()
            r = session.get(ARXIV_API, params=params, timeout=60)
            r.raise_for_status()
            return feedparser.parse(r.text), had_rate_limit
        except requests.exceptions.HTTPError as e:
            last_exc = e
            status_code = e.response.status_code if e.response is not None else None
            if status_code == 429:
                had_rate_limit = True
                retry_after = None
                if e.response is not None:
                    retry_after = parse_retry_after(e.response.headers.get("Retry-After"))
                if attempt >= retries:
                    raise RateLimitExhausted(
                        f"arXiv rate limit (429) after {retries} attempts"
                    ) from e
                wait = compute_429_wait(
                    attempt,
                    retry_after,
                    base_wait=base_429_wait,
                    max_wait=max_429_wait,
                )
                logger.warning(
                    "Rate limited 429 (attempt %d/%d); waiting %.0fs before retry.",
                    attempt, retries, wait,
                )
                time.sleep(wait)
            else:
                logger.warning("Request failed (attempt %d/%d): %s", attempt, retries, repr(e))
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2
        except RateLimitExhausted:
            raise
        except Exception as e:
            last_exc = e
            logger.warning("Request failed (attempt %d/%d): %s", attempt, retries, repr(e))
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("fetch_page_with_retry ended without result")


@dataclass
class Paper:
    title: str
    published_utc: datetime
    arxiv_id: str
    link: str
    authors: List[str]
    summary: str
    paper_categories: List[str] = None
    comments: str = ""
    journal_ref: str = ""
    report_no: str = ""
    created_date: str = ""
    updated_date: str = ""
    affiliations: List[str] = None

    def __post_init__(self):
        if self.paper_categories is None:
            self.paper_categories = []
        if self.affiliations is None:
            self.affiliations = []


_LOCAL_QUERY_TOKEN_RE = re.compile(
    r'''\s*(?:(ANDNOT|AND|OR)\b|([()])|'''
    r'''(?:([A-Za-z][A-Za-z0-9_-]*)\s*:)?("(?:\\.|[^"])*"|[^\s()]+))''',
    re.IGNORECASE,
)
_LOCAL_QUERY_FIELDS = {
    "all": "all",
    "ti": "title",
    "title": "title",
    "abs": "abstract",
    "abstract": "abstract",
    "au": "author",
    "author": "author",
    "cat": "category",
    "category": "category",
    "id": "id",
    "co": "comments",
    "jr": "journal_ref",
    "rn": "report_no",
}


def _tokenize_local_arxiv_query(user_query: str) -> List[tuple]:
    query = build_text_clause(user_query)
    if not query:
        return []

    tokens: List[tuple] = []
    position = 0
    while position < len(query):
        match = _LOCAL_QUERY_TOKEN_RE.match(query, position)
        if match is None:
            if not query[position:].strip():
                break
            raise ValueError(
                f"unsupported local arXiv query syntax near {query[position:position + 24]!r}"
            )
        operator, parenthesis, raw_field, raw_value = match.groups()
        position = match.end()
        if operator:
            tokens.append((operator.upper(), None))
            continue
        if parenthesis:
            tokens.append(("LPAREN" if parenthesis == "(" else "RPAREN", None))
            continue

        field = (raw_field or "all").lower()
        if field not in _LOCAL_QUERY_FIELDS:
            raise ValueError(
                f"arXiv query field {field!r} cannot be evaluated from OAI metadata"
            )
        value = raw_value or ""
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            value = value[1:-1].replace(r'\"', '"').replace(r"\\", "\\")
        value = normalize_text(value)
        if not value:
            raise ValueError("arXiv query terms cannot be empty")
        tokens.append(("TERM", (_LOCAL_QUERY_FIELDS[field], value)))

    with_implicit_and: List[tuple] = []
    for token in tokens:
        if with_implicit_and:
            previous = with_implicit_and[-1][0]
            current = token[0]
            if previous in {"TERM", "RPAREN"} and current in {"TERM", "LPAREN"}:
                with_implicit_and.append(("AND", None))
        with_implicit_and.append(token)
    return with_implicit_and


def _compile_local_arxiv_query(user_query: str):
    tokens = _tokenize_local_arxiv_query(user_query)
    if not tokens:
        return None
    position = 0

    def parse_factor():
        nonlocal position
        if position >= len(tokens):
            raise ValueError("arXiv query ended before a term")
        token_type, value = tokens[position]
        if token_type == "TERM":
            position += 1
            return ("TERM", value)
        if token_type == "LPAREN":
            position += 1
            node = parse_or()
            if position >= len(tokens) or tokens[position][0] != "RPAREN":
                raise ValueError("arXiv query contains an unmatched '('")
            position += 1
            return node
        raise ValueError(f"unexpected {token_type} in arXiv query")

    def parse_and():
        nonlocal position
        node = parse_factor()
        while position < len(tokens) and tokens[position][0] in {"AND", "ANDNOT"}:
            operator = tokens[position][0]
            position += 1
            node = (operator, node, parse_factor())
        return node

    def parse_or():
        nonlocal position
        node = parse_and()
        while position < len(tokens) and tokens[position][0] == "OR":
            position += 1
            node = ("OR", node, parse_and())
        return node

    compiled = parse_or()
    if position != len(tokens):
        raise ValueError(f"unexpected {tokens[position][0]} in arXiv query")
    return compiled


def _local_term_matches(haystack: str, needle: str) -> bool:
    normalized_haystack = normalize_text(haystack).casefold()
    normalized_needle = normalize_text(needle).casefold()
    if "*" not in normalized_needle and "?" not in normalized_needle:
        return normalized_needle in normalized_haystack
    wildcard = re.escape(normalized_needle)
    wildcard = wildcard.replace(r"\*", ".*").replace(r"\?", ".")
    return re.search(wildcard, normalized_haystack, re.DOTALL) is not None


def _paper_matches_local_query_node(paper: Paper, node) -> bool:
    operator = node[0]
    if operator == "AND":
        return _paper_matches_local_query_node(
            paper, node[1]
        ) and _paper_matches_local_query_node(paper, node[2])
    if operator == "ANDNOT":
        return _paper_matches_local_query_node(
            paper, node[1]
        ) and not _paper_matches_local_query_node(paper, node[2])
    if operator == "OR":
        return _paper_matches_local_query_node(
            paper, node[1]
        ) or _paper_matches_local_query_node(paper, node[2])

    field, value = node[1]
    if field == "title":
        return _local_term_matches(paper.title, value)
    if field == "abstract":
        return _local_term_matches(paper.summary, value)
    if field == "author":
        return _local_term_matches(" ".join(paper.authors), value)
    if field == "category":
        return any(_local_term_matches(category, value) for category in paper.paper_categories)
    if field == "id":
        return _local_term_matches(paper.arxiv_id, value)
    if field == "comments":
        return _local_term_matches(paper.comments, value)
    if field == "journal_ref":
        return _local_term_matches(paper.journal_ref, value)
    if field == "report_no":
        return _local_term_matches(paper.report_no, value)
    searchable = " ".join(
        [
            paper.title,
            paper.summary,
            " ".join(paper.authors),
            " ".join(paper.paper_categories),
            paper.arxiv_id,
            paper.comments,
            paper.journal_ref,
            paper.report_no,
        ]
    )
    return _local_term_matches(searchable, value)


def filter_papers_by_local_arxiv_query(
    papers: List[Paper], user_query: str
) -> List[Paper]:
    """Evaluate common arXiv query syntax over complete OAI metadata."""
    compiled = _compile_local_arxiv_query(user_query)
    if compiled is None:
        return papers
    return [
        paper
        for paper in papers
        if _paper_matches_local_query_node(paper, compiled)
    ]


def oai_set_spec_for_category(category: str) -> str:
    """Map ``cs.AI`` to arXiv OAI's official ``cs:cs:AI`` hierarchy."""
    value = (category or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", value):
        raise ValueError(f"invalid arXiv category for OAI set: {category!r}")
    archive = value.split(".", 1)[0]
    return f"{archive}:{value.replace('.', ':')}"


def _oai_child_text(element, namespace: str, name: str) -> str:
    child = element.find(f"{{{namespace}}}{name}")
    return normalize_text(child.text if child is not None else "")


def paper_from_oai_record(record, announcement_date: date) -> Optional[Paper]:
    header = record.find(f"{{{_OAI_NAMESPACE}}}header")
    if header is None or header.attrib.get("status") == "deleted":
        return None
    metadata = record.find(f"{{{_OAI_NAMESPACE}}}metadata")
    if metadata is None:
        return None
    arxiv = metadata.find(f"{{{_ARXIV_OAI_NAMESPACE}}}arXiv")
    if arxiv is None:
        return None

    paper_id = arxiv_id_from_entry_url(
        _oai_child_text(arxiv, _ARXIV_OAI_NAMESPACE, "id")
        or _oai_child_text(header, _OAI_NAMESPACE, "identifier")
    )
    if not paper_id:
        return None

    authors: List[str] = []
    affiliations: List[str] = []
    authors_node = arxiv.find(f"{{{_ARXIV_OAI_NAMESPACE}}}authors")
    if authors_node is not None:
        for author in authors_node.findall(f"{{{_ARXIV_OAI_NAMESPACE}}}author"):
            forenames = _oai_child_text(
                author, _ARXIV_OAI_NAMESPACE, "forenames"
            )
            keyname = _oai_child_text(author, _ARXIV_OAI_NAMESPACE, "keyname")
            suffix = _oai_child_text(author, _ARXIV_OAI_NAMESPACE, "suffix")
            name = normalize_text(" ".join(part for part in (forenames, keyname, suffix) if part))
            if name:
                authors.append(name)
            for affiliation in author.findall(
                f"{{{_ARXIV_OAI_NAMESPACE}}}affiliation"
            ):
                value = normalize_text(affiliation.text or "")
                if value and value not in affiliations:
                    affiliations.append(value)

    categories = _oai_child_text(
        arxiv, _ARXIV_OAI_NAMESPACE, "categories"
    ).split()
    return Paper(
        title=_oai_child_text(arxiv, _ARXIV_OAI_NAMESPACE, "title"),
        published_utc=datetime.combine(
            announcement_date,
            dtime(0, 0),
            tzinfo=timezone.utc,
        ),
        arxiv_id=paper_id,
        link=f"https://arxiv.org/abs/{paper_id}",
        authors=authors,
        summary=_oai_child_text(arxiv, _ARXIV_OAI_NAMESPACE, "abstract"),
        paper_categories=categories,
        comments=_oai_child_text(arxiv, _ARXIV_OAI_NAMESPACE, "comments"),
        journal_ref=_oai_child_text(arxiv, _ARXIV_OAI_NAMESPACE, "journal-ref"),
        report_no=_oai_child_text(arxiv, _ARXIV_OAI_NAMESPACE, "report-no"),
        created_date=_oai_child_text(arxiv, _ARXIV_OAI_NAMESPACE, "created"),
        updated_date=_oai_child_text(arxiv, _ARXIV_OAI_NAMESPACE, "updated"),
        affiliations=affiliations,
    )


def parse_oai_records(
    payload: bytes | str, announcement_date: date
) -> Tuple[List[Paper], str]:
    root = ET.fromstring(payload)
    for error in root.findall(f"{{{_OAI_NAMESPACE}}}error"):
        code = (error.attrib.get("code") or "").strip()
        if code in {"noRecordsMatch", "idDoesNotExist"}:
            return [], ""
        detail = normalize_text(error.text or "")
        raise ValueError(f"arXiv OAI error {code or 'unknown'}: {detail}")

    papers: List[Paper] = []
    for record in root.findall(f".//{{{_OAI_NAMESPACE}}}record"):
        paper = paper_from_oai_record(record, announcement_date)
        if paper is not None:
            papers.append(paper)
    token_node = root.find(f".//{{{_OAI_NAMESPACE}}}resumptionToken")
    token = normalize_text(token_node.text if token_node is not None else "")
    return papers, token


def fetch_oai_xml_with_retry(
    session: requests.Session,
    params: dict,
    logger,
    retries: int = 5,
    *,
    base_429_wait: float = ARXIV_429_BASE_WAIT,
    max_429_wait: float = ARXIV_429_MAX_WAIT,
) -> bytes:
    backoff = 1.0
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            wait_before_request()
            response = session.get(ARXIV_OAI_URL, params=params, timeout=60)
            response.raise_for_status()
            ET.fromstring(response.content)
            return response.content
        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code == 429:
                if attempt >= retries:
                    raise RateLimitExhausted(
                        f"arXiv OAI rate limit (429) after {retries} attempts"
                    ) from exc
                retry_after = (
                    parse_retry_after(exc.response.headers.get("Retry-After"))
                    if exc.response is not None
                    else None
                )
                wait = compute_429_wait(
                    attempt,
                    retry_after,
                    base_wait=base_429_wait,
                    max_wait=max_429_wait,
                )
                logger.warning(
                    "OAI rate limited (attempt %d/%d); waiting %.0fs.",
                    attempt,
                    retries,
                    wait,
                )
                time.sleep(wait)
            else:
                logger.warning(
                    "OAI request failed (attempt %d/%d): %s",
                    attempt,
                    retries,
                    repr(exc),
                )
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2
        except RateLimitExhausted:
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "OAI request failed (attempt %d/%d): %s",
                attempt,
                retries,
                repr(exc),
            )
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("fetch_oai_xml_with_retry ended without result")


def fetch_oai_category_records(
    session: requests.Session,
    category: str,
    announcement_date: date,
    logger,
    *,
    retries: int,
    base_429_wait: float,
    max_429_wait: float,
) -> List[Paper]:
    date_string = announcement_date.isoformat()
    params = {
        "verb": "ListRecords",
        "from": date_string,
        "until": date_string,
        "set": oai_set_spec_for_category(category),
        "metadataPrefix": "arXiv",
    }
    by_id: dict[str, Paper] = {}
    for page_index in range(100):
        payload = fetch_oai_xml_with_retry(
            session,
            params,
            logger,
            retries=retries,
            base_429_wait=base_429_wait,
            max_429_wait=max_429_wait,
        )
        papers, token = parse_oai_records(payload, announcement_date)
        by_id.update((paper.arxiv_id, paper) for paper in papers)
        if not token:
            return list(by_id.values())
        params = {"verb": "ListRecords", "resumptionToken": token}
    raise AnnouncementMetadataIncomplete(
        f"arXiv OAI pagination exceeded 100 pages for {category}"
    )


def fetch_oai_record(
    session: requests.Session,
    paper_id: str,
    announcement_date: date,
    logger,
    *,
    retries: int,
    base_429_wait: float,
    max_429_wait: float,
) -> Optional[Paper]:
    payload = fetch_oai_xml_with_retry(
        session,
        {
            "verb": "GetRecord",
            "identifier": f"oai:arXiv.org:{paper_id}",
            "metadataPrefix": "arXiv",
        },
        logger,
        retries=retries,
        base_429_wait=base_429_wait,
        max_429_wait=max_429_wait,
    )
    papers, _ = parse_oai_records(payload, announcement_date)
    return papers[0] if papers else None


def parse_new_listing_page(page_html: str) -> Tuple[date, List[str]]:
    """Extract one category's new/cross IDs and its official listing date."""
    heading_matches = list(
        re.finditer(r"<h3[^>]*>(.*?)</h3>", page_html or "", re.IGNORECASE | re.DOTALL)
    )
    if not heading_matches:
        raise ValueError("arXiv new-listing page did not contain any h3 headings")

    heading_texts = [
        normalize_text(unescape(re.sub(r"<[^>]+>", " ", match.group(1))))
        for match in heading_matches
    ]
    batch_heading = next(
        (text for text in heading_texts if text.startswith("Showing new listings for ")),
        "",
    )
    if not batch_heading:
        raise ValueError("arXiv new-listing page did not identify its batch date")
    raw_date = batch_heading.removeprefix("Showing new listings for ").strip()
    parsed_date = parsedate_to_datetime(f"{raw_date} 00:00:00 GMT")
    if parsed_date is None:
        raise ValueError(f"invalid arXiv new-listing date: {raw_date!r}")

    paper_ids: List[str] = []
    for index, (match, heading_text) in enumerate(zip(heading_matches, heading_texts)):
        if not heading_text.startswith(("New submissions", "Cross submissions")):
            continue
        count_match = re.search(
            r"showing(?:\s+first)?\s+(\d+)\s+of\s+(\d+)\s+entries",
            heading_text,
            re.IGNORECASE,
        )
        if count_match and int(count_match.group(1)) < int(count_match.group(2)):
            raise AnnouncementMetadataIncomplete(
                f"arXiv listing section was truncated: {heading_text}"
            )
        block_end = (
            heading_matches[index + 1].start()
            if index + 1 < len(heading_matches)
            else len(page_html)
        )
        block = page_html[match.end():block_end]
        for raw_id in re.findall(
            r"href\s*=\s*[\"']\s*/abs/([^\"'?#]+)",
            block,
            re.IGNORECASE,
        ):
            paper_id = arxiv_id_from_entry_url(f"/abs/{raw_id.strip()}")
            if paper_id:
                paper_ids.append(paper_id)
    return parsed_date.date(), list(dict.fromkeys(paper_ids))


def parse_pastweek_listing_page(
    page_html: str,
    requested_date: date,
    category: str,
) -> List[str]:
    """Extract one exact new+cross day from an official ``pastweek`` page."""
    heading_matches = list(
        re.finditer(r"<h3[^>]*>(.*?)</h3>", page_html or "", re.IGNORECASE | re.DOTALL)
    )
    available_dates: List[date] = []
    for index, match in enumerate(heading_matches):
        heading_text = normalize_text(unescape(re.sub(r"<[^>]+>", " ", match.group(1))))
        date_match = re.match(
            r"^([A-Z][a-z]{2},\s+\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})\s+"
            r"\(showing(?:\s+first)?\s+(\d+)\s+of\s+(\d+)\s+entries\s*\)$",
            heading_text,
        )
        if not date_match:
            continue
        parsed = parsedate_to_datetime(f"{date_match.group(1)} 00:00:00 GMT")
        if parsed is None:
            continue
        heading_date = parsed.date()
        available_dates.append(heading_date)
        if heading_date != requested_date:
            continue
        shown_count = int(date_match.group(2))
        total_count = int(date_match.group(3))
        if shown_count < total_count:
            raise AnnouncementMetadataIncomplete(
                f"arXiv pastweek section was truncated: {heading_text}"
            )
        block_end = (
            heading_matches[index + 1].start()
            if index + 1 < len(heading_matches)
            else len(page_html)
        )
        block = page_html[match.end():block_end]
        paper_ids = [
            arxiv_id_from_entry_url(f"/abs/{raw_id.strip()}")
            for raw_id in re.findall(
                r"href\s*=\s*[\"']\s*/abs/([^\"'?#]+)",
                block,
                re.IGNORECASE,
            )
        ]
        paper_ids = list(dict.fromkeys(paper_id for paper_id in paper_ids if paper_id))
        if len(paper_ids) != shown_count:
            raise AnnouncementMetadataIncomplete(
                f"arXiv pastweek count mismatch for {category} on "
                f"{requested_date.isoformat()}: expected {shown_count}, parsed {len(paper_ids)}"
            )
        return paper_ids

    if available_dates:
        raise AnnouncementBatchNotReady(
            requested_date,
            max(available_dates),
            category,
        )
    raise ValueError(f"arXiv pastweek page contained no dated sections for {category}")


def _fetch_listing_page_with_retry(
    session: requests.Session,
    category: str,
    period: str,
    logger,
    retries: int = 5,
    *,
    base_429_wait: float = ARXIV_429_BASE_WAIT,
    max_429_wait: float = ARXIV_429_MAX_WAIT,
) -> str:
    """Fetch one complete official category listing page."""
    if period not in {"new", "pastweek"}:
        raise ValueError(f"unsupported arXiv listing period: {period!r}")
    url = f"https://arxiv.org/list/{quote(category, safe='.')}/{period}"
    params = {"skip": 0, "show": 2000}
    backoff = 1.0
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            wait_before_request()
            response = session.get(url, params=params, timeout=60)
            response.raise_for_status()
            required_marker = (
                "Showing new listings for " if period == "new" else "entries per page"
            )
            if required_marker not in response.text:
                raise ValueError(
                    f"invalid arXiv {period} listing HTML for {category}"
                )
            return response.text
        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code == 429:
                if attempt >= retries:
                    raise RateLimitExhausted(
                        f"arXiv listing rate limit (429) after {retries} attempts"
                    ) from exc
                retry_after = (
                    parse_retry_after(exc.response.headers.get("Retry-After"))
                    if exc.response is not None
                    else None
                )
                wait = compute_429_wait(
                    attempt,
                    retry_after,
                    base_wait=base_429_wait,
                    max_wait=max_429_wait,
                )
                logger.warning(
                    "%s listing rate limited for %s (attempt %d/%d); waiting %.0fs.",
                    period,
                    category,
                    attempt,
                    retries,
                    wait,
                )
                time.sleep(wait)
            else:
                logger.warning(
                    "%s listing request failed for %s (attempt %d/%d): %s",
                    period,
                    category,
                    attempt,
                    retries,
                    repr(exc),
                )
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2
        except RateLimitExhausted:
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "%s listing request failed for %s (attempt %d/%d): %s",
                period,
                category,
                attempt,
                retries,
                repr(exc),
            )
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("_fetch_listing_page_with_retry ended without result")


def fetch_new_listing_with_retry(
    session: requests.Session,
    category: str,
    logger,
    retries: int = 5,
    *,
    base_429_wait: float = ARXIV_429_BASE_WAIT,
    max_429_wait: float = ARXIV_429_MAX_WAIT,
) -> str:
    return _fetch_listing_page_with_retry(
        session,
        category,
        "new",
        logger,
        retries=retries,
        base_429_wait=base_429_wait,
        max_429_wait=max_429_wait,
    )


def fetch_pastweek_listing_with_retry(
    session: requests.Session,
    category: str,
    logger,
    retries: int = 5,
    *,
    base_429_wait: float = ARXIV_429_BASE_WAIT,
    max_429_wait: float = ARXIV_429_MAX_WAIT,
) -> str:
    return _fetch_listing_page_with_retry(
        session,
        category,
        "pastweek",
        logger,
        retries=retries,
        base_429_wait=base_429_wait,
        max_429_wait=max_429_wait,
    )


def fetch_metadata_for_announcement_ids(
    session: requests.Session,
    paper_ids: List[str],
    categories: List[str],
    announcement_date: date,
    user_query: str,
    logger,
    *,
    retries: int,
    sleep_seconds: float,
    base_429_wait: float,
    max_429_wait: float,
) -> List[Paper]:
    """Hydrate exact listing IDs from OAI, then apply the query locally."""
    if not paper_ids:
        return []

    by_id: dict[str, Paper] = {}
    unique_categories = list(dict.fromkeys(
        category.strip() for category in categories if category.strip()
    ))
    for index, category in enumerate(unique_categories):
        records = fetch_oai_category_records(
            session,
            category,
            announcement_date,
            logger,
            retries=retries,
            base_429_wait=base_429_wait,
            max_429_wait=max_429_wait,
        )
        by_id.update((paper.arxiv_id, paper) for paper in records)
        if index + 1 < len(unique_categories):
            time.sleep(sleep_seconds)

    missing = [paper_id for paper_id in paper_ids if paper_id not in by_id]
    logger.info(
        "OAI daily metadata covered %d/%d listed papers; %d cross-list gap(s) "
        "need GetRecord.",
        len(paper_ids) - len(missing),
        len(paper_ids),
        len(missing),
    )
    acceptable_gap = max(8, int(len(paper_ids) * 0.10))
    if len(missing) > acceptable_gap:
        raise AnnouncementMetadataIncomplete(
            f"arXiv OAI daily metadata is not ready: {len(missing)} of "
            f"{len(paper_ids)} listed papers are absent"
        )

    # Cross-lists can be older papers whose OAI datestamp is not today's date.
    # GetRecord fills only that small, bounded gap without reverting to the
    # currently unreachable export Atom API.
    for paper_id in missing:
        paper = fetch_oai_record(
            session,
            paper_id,
            announcement_date,
            logger,
            retries=retries,
            base_429_wait=base_429_wait,
            max_429_wait=max_429_wait,
        )
        if paper is not None:
            by_id[paper.arxiv_id] = paper

    still_missing = [paper_id for paper_id in paper_ids if paper_id not in by_id]
    if still_missing:
        raise AnnouncementMetadataIncomplete(
            f"arXiv OAI metadata missing for {len(still_missing)} listed papers "
            f"(sample: {', '.join(still_missing[:3])})"
        )

    ordered = [by_id[paper_id] for paper_id in paper_ids]
    return filter_papers_by_local_arxiv_query(ordered, user_query)


def fetch_official_new_listing_batch(
    session: requests.Session,
    categories: List[str],
    requested_date: date,
    user_query: str,
    logger,
    *,
    max_papers: int,
    retries: int,
    sleep_seconds: float,
    base_429_wait: float,
    max_429_wait: float,
) -> Tuple[List[Paper], int, dict]:
    """Fetch exact new/cross IDs from official new/pastweek listings plus OAI."""
    if requested_date.weekday() >= 5:
        return [], 0, {}

    all_ids = set()
    listing_dates: dict[str, str] = {}
    use_pastweek = False
    for index, category in enumerate(categories):
        if use_pastweek:
            pastweek_html = fetch_pastweek_listing_with_retry(
                session,
                category,
                logger,
                retries=retries,
                base_429_wait=base_429_wait,
                max_429_wait=max_429_wait,
            )
            category_ids = parse_pastweek_listing_page(
                pastweek_html,
                requested_date,
                category,
            )
        else:
            page_html = fetch_new_listing_with_retry(
                session,
                category,
                logger,
                retries=retries,
                base_429_wait=base_429_wait,
                max_429_wait=max_429_wait,
            )
            available_date, category_ids = parse_new_listing_page(page_html)
            if available_date != requested_date:
                use_pastweek = True
                pastweek_html = fetch_pastweek_listing_with_retry(
                    session,
                    category,
                    logger,
                    retries=retries,
                    base_429_wait=base_429_wait,
                    max_429_wait=max_429_wait,
                )
                category_ids = parse_pastweek_listing_page(
                    pastweek_html,
                    requested_date,
                    category,
                )
        listing_dates[category] = requested_date.isoformat()
        all_ids.update(category_ids)
        if index + 1 < len(categories):
            time.sleep(sleep_seconds)

    sorted_ids = sorted(all_ids, key=arxiv_id_sort_key, reverse=True)
    candidate_count = len(sorted_ids)
    if not user_query.strip():
        sorted_ids = sorted_ids[:max(0, max_papers)]
    papers = fetch_metadata_for_announcement_ids(
        session,
        sorted_ids,
        categories,
        requested_date,
        user_query,
        logger,
        retries=retries,
        sleep_seconds=sleep_seconds,
        base_429_wait=base_429_wait,
        max_429_wait=max_429_wait,
    )
    return papers[:max(0, max_papers)], candidate_count, listing_dates


def fetch_rss_feed_with_retry(
    session: requests.Session,
    category: str,
    logger,
    retries: int = 5,
    *,
    base_429_wait: float = ARXIV_429_BASE_WAIT,
    max_429_wait: float = ARXIV_429_MAX_WAIT,
):
    """Fetch one official category RSS feed with all-or-nothing retries."""
    base_url = os.environ.get("ARXIV_RSS_BASE_URL", ARXIV_RSS_BASE_URL).rstrip("/")
    url = f"{base_url}/{quote(category, safe='.')}"
    backoff = 1.0
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            wait_before_request()
            response = session.get(url, timeout=60)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            if getattr(feed, "bozo", False) and not getattr(feed, "entries", None):
                raise ValueError(
                    f"invalid RSS XML for {category}: {getattr(feed, 'bozo_exception', '')}"
                )
            return feed
        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code == 429:
                if attempt >= retries:
                    raise RateLimitExhausted(
                        f"arXiv RSS rate limit (429) after {retries} attempts"
                    ) from exc
                retry_after = (
                    parse_retry_after(exc.response.headers.get("Retry-After"))
                    if exc.response is not None
                    else None
                )
                wait = compute_429_wait(
                    attempt,
                    retry_after,
                    base_wait=base_429_wait,
                    max_wait=max_429_wait,
                )
                logger.warning(
                    "RSS rate limited for %s (attempt %d/%d); waiting %.0fs.",
                    category,
                    attempt,
                    retries,
                    wait,
                )
                time.sleep(wait)
            else:
                logger.warning(
                    "RSS request failed for %s (attempt %d/%d): %s",
                    category,
                    attempt,
                    retries,
                    repr(exc),
                )
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2
        except RateLimitExhausted:
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "RSS request failed for %s (attempt %d/%d): %s",
                category,
                attempt,
                retries,
                repr(exc),
            )
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("fetch_rss_feed_with_retry ended without result")


def filter_papers_by_arxiv_query(
    session: requests.Session,
    papers: List[Paper],
    user_query: str,
    logger,
    *,
    retries: int,
    sleep_seconds: float,
    base_429_wait: float,
    max_429_wait: float,
) -> List[Paper]:
    """Apply the existing arXiv query grammar to an RSS-discovered ID set."""
    text_clause = build_text_clause(user_query)
    if not text_clause or not papers:
        return papers

    matching_ids = set()
    chunk_size = 100
    for offset in range(0, len(papers), chunk_size):
        chunk = papers[offset:offset + chunk_size]
        params = {
            "search_query": text_clause,
            "id_list": ",".join(p.arxiv_id for p in chunk),
            "start": 0,
            "max_results": len(chunk),
        }
        feed, _ = fetch_page_with_retry(
            session,
            params,
            logger,
            retries=retries,
            base_429_wait=base_429_wait,
            max_429_wait=max_429_wait,
        )
        matching_ids.update(
            arxiv_id_from_entry_url(str(_feed_value(entry, "id", "")))
            for entry in feed.entries
        )
        if offset + chunk_size < len(papers):
            time.sleep(sleep_seconds)
    return [paper for paper in papers if paper.arxiv_id in matching_ids]


def fetch_official_announcement_batch(
    session: requests.Session,
    categories: List[str],
    requested_date: date,
    user_query: str,
    logger,
    *,
    retries: int,
    sleep_seconds: float,
    base_429_wait: float,
    max_429_wait: float,
) -> Tuple[List[Paper], int, dict]:
    """Fetch the exact arXiv announcement batch named by ``requested_date``.

    RSS ``pubDate`` identifies the release batch, unlike Atom ``published``,
    which is the initial submission/processing timestamp and can move papers
    across China calendar-day boundaries.
    """
    if requested_date.weekday() >= 5:
        return [], 0, {}

    by_id: dict[str, Paper] = {}
    feed_dates: dict[str, str] = {}
    unknown_announce_types = 0
    for index, category in enumerate(categories):
        feed = fetch_rss_feed_with_retry(
            session,
            category,
            logger,
            retries=retries,
            base_429_wait=base_429_wait,
            max_429_wait=max_429_wait,
        )
        available_date = parse_rss_batch_date(feed)
        feed_dates[category] = available_date.isoformat()
        if available_date != requested_date:
            raise AnnouncementBatchNotReady(requested_date, available_date, category)

        for entry in feed.entries:
            announce_type = parse_rss_announce_type(entry)
            if announce_type and announce_type not in _RSS_INCLUDED_ANNOUNCE_TYPES:
                continue
            if not announce_type:
                unknown_announce_types += 1
            paper = paper_from_rss_entry(entry, requested_date)
            if not paper.arxiv_id:
                continue
            existing = by_id.get(paper.arxiv_id)
            if existing is None:
                by_id[paper.arxiv_id] = paper
            else:
                existing.paper_categories = list(dict.fromkeys(
                    existing.paper_categories + paper.paper_categories
                ))
        if index + 1 < len(categories):
            time.sleep(sleep_seconds)

    if unknown_announce_types:
        logger.warning(
            "%d RSS entries did not expose announce_type; retained conservatively.",
            unknown_announce_types,
        )
    papers = list(by_id.values())
    candidate_count = len(papers)
    papers = filter_papers_by_arxiv_query(
        session,
        papers,
        user_query,
        logger,
        retries=retries,
        sleep_seconds=sleep_seconds,
        base_429_wait=base_429_wait,
        max_429_wait=max_429_wait,
    )
    papers.sort(key=lambda paper: arxiv_id_sort_key(paper.arxiv_id), reverse=True)
    return papers, candidate_count, feed_dates


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", "-q", default="", help="自然语言 or 高级表达式（ti:/abs:/AND/...）。自然语言将按 all: 逐词 AND 处理。")
    ap.add_argument("--categories", "-c", default=",".join(SEARCH_CATEGORIES), help="逗号分隔的分类，如 cs.AI,cs.LG")
    ap.add_argument("--start", required=False, default="", help="UTC 起始：YYYY-MM-DD 或 ISO8601（如 2026-01-19T00:00:00Z）")
    ap.add_argument("--end", required=False, default="", help="UTC 结束（右开）：YYYY-MM-DD 或 ISO8601。若是 YYYY-MM-DD，则解释为“包含该日”，自动+1天")
    ap.add_argument("--anchor-tz", default="Asia/Shanghai", help="锚定时区：以该时区的当天 00:00 换算为 UTC 作为 end")
    ap.add_argument("--days", type=int, default=1, help="当未提供 start/end 时，从锚定 00:00 往前推 days 天")
    ap.add_argument("--anchor-date", default="", help="锚定日期 YYYY-MM-DD（按 anchor-tz 的这天 00:00 作为 end）；为空则用 anchor-tz 的今天")
    ap.add_argument("--last-hours", type=float, default=None, help="可选：当未提供 start/end 时，用 now_utc - last_hours 到 now_utc（与锚定 00:00 互斥）")
    ap.add_argument("--page-size", type=int, default=PAGE_SIZE_DEFAULT, help="每页数量（<=2000）")
    ap.add_argument("--max-papers", type=int, default=MAX_PAPERS_DEFAULT, help="最多返回多少篇")
    ap.add_argument("--sleep", type=float, default=SLEEP_DEFAULT, help="分页间隔秒数（建议 >=3，尊重 arXiv）")
    ap.add_argument("--retries", type=int, default=RETRY_COUNT, help="请求失败重试次数（指数退避）")
    ap.add_argument("--429-base-wait", dest="base_429_wait", type=float, default=ARXIV_429_BASE_WAIT, help="429 退避基数（秒）")
    ap.add_argument("--429-max-wait", dest="max_429_wait", type=float, default=ARXIV_429_MAX_WAIT, help="429 退避上限（秒）")
    ap.add_argument("--no-single-line-progress", action="store_true", help="禁用单行进度显示")
    ap.add_argument("--user-agent", default=ARXIV_USER_AGENT, help="User-Agent（建议含联系信息）")
    ap.add_argument("--use-proxy", action="store_true", default=USE_PROXY_DEFAULT, help="是否允许读取环境变量代理")
    ap.add_argument("--out", default="", help="输出 markdown 文件路径；为空则写入 data/arxivList/md")
    ap.add_argument("--out-json", default="", help="输出 json 文件路径；为空则写入 data/arxivList/json")
    return ap.parse_args()


def run():
    print("START arxiv_search.py", flush=True)
    logger = setup_logging()
    args = parse_args()

    used_anchor_window = False
    anchor_date_for_name: Optional[date] = None

    if args.start.strip() and args.end.strip():
        start_utc = _parse_utc_datetime(args.start, is_end=False)
        end_utc = _parse_utc_datetime(args.end, is_end=True)
    else:
        if args.last_hours is not None:
            end_utc = datetime.now(timezone.utc)
            start_utc = end_utc - timedelta(hours=float(args.last_hours))
        else:
            used_anchor_window = True
            if ZoneInfo is not None:
                tz = ZoneInfo(str(args.anchor_tz))
                if args.anchor_date.strip():
                    anchor_date_for_name = date.fromisoformat(args.anchor_date.strip())
                else:
                    anchor_date_for_name = datetime.now(tz).date()
            start_utc, end_utc = compute_window_by_midnight_anchor(
                anchor_tz=str(args.anchor_tz),
                days=int(args.days),
                anchor_date_str=(args.anchor_date.strip() or None),
            )

    if end_utc <= start_utc:
        raise SystemExit(f"end must be greater than start (start={start_utc.isoformat()} end={end_utc.isoformat()})")

    categories = [c.strip() for c in (args.categories or "").split(",") if c.strip()]
    search_query = build_search_query(
        categories=categories,
        user_query=args.query,
        start_utc=start_utc,
        end_utc=end_utc,
    )

    logger.info("Timezone: %s", "UTC")
    logger.info(
        "Window  : %s -> %s",
        start_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        end_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
    )

    session = build_arxiv_api_session(prefer_env_proxy=bool(args.use_proxy))
    if args.user_agent:
        session.headers.update({"User-Agent": str(args.user_agent)})
    logger.info("Proxy from env enabled: %s", bool(args.use_proxy))

    results: List[Paper] = []
    source_mode = "submitted_date_api"
    announcement_source_dates: dict[str, str] = {}
    start_idx = 0
    page_size = max(1, min(args.page_size, 2000))
    candidates = 0
    pages = 0
    # True if any page fetch encountered a 429 rate-limit response.
    any_rate_limited = False
    rate_limit_partial = False
    print("============开始获取初始可下载列表==============", flush=True)

    announcement_loaded = False
    use_announcement_source = bool(
        used_anchor_window
        and anchor_date_for_name is not None
        and int(args.days) == 1
        and categories
    )
    if use_announcement_source:
        try:
            results, candidates, announcement_source_dates = (
                fetch_official_new_listing_batch(
                    session,
                    categories,
                    anchor_date_for_name,
                    args.query,
                    logger,
                    max_papers=int(args.max_papers),
                    retries=int(args.retries),
                    sleep_seconds=float(args.sleep),
                    base_429_wait=float(args.base_429_wait),
                    max_429_wait=float(args.max_429_wait),
                )
            )
            source_mode = "official_listing_oai"
            announcement_loaded = True
            results = results[:max(0, int(args.max_papers))]
            logger.info(
                "Official announcement batch %s: %d unique candidates, %d selected.",
                anchor_date_for_name.isoformat(),
                candidates,
                len(results),
            )
        except AnnouncementBatchNotReady as exc:
            if ZoneInfo is None:
                local_today = datetime.now().date()
            else:
                local_today = datetime.now(ZoneInfo(str(args.anchor_tz))).date()
            state = (
                "has not been published yet"
                if anchor_date_for_name >= local_today
                else "is outside the official recent-listing window"
            )
            logger.warning(
                "Exact arXiv batch %s (%s; %s). Exiting with code %d so it "
                "remains retryable instead of substituting an approximate "
                "submitted-date query.",
                state,
                exc,
                anchor_date_for_name.isoformat(),
                ARXIV_EXIT_BATCH_NOT_READY,
            )
            raise SystemExit(ARXIV_EXIT_BATCH_NOT_READY) from exc
        except AnnouncementMetadataIncomplete as exc:
            logger.warning(
                "Official listing is available but OAI metadata is incomplete (%s). "
                "Exiting with code %d so the scheduler retries instead of "
                "publishing a partial or empty day.",
                exc,
                ARXIV_EXIT_BATCH_NOT_READY,
            )
            raise SystemExit(ARXIV_EXIT_BATCH_NOT_READY) from exc
        except RateLimitExhausted as exc:
            logger.warning("arXiv rate limit exhausted: %s", exc)
            raise SystemExit(2) from exc

    if not announcement_loaded:
        while len(results) < args.max_papers:
            pages += 1
            msg = f"[INFO] Fetch page 【{pages}】 (start={start_idx}, max_results={page_size}) ..."
            single_line = PROGRESS_SINGLE_LINE and (not bool(args.no_single_line_progress)) and sys.stdout.isatty()
            if single_line:
                sys.stdout.write(msg + "\r")
                sys.stdout.flush()
            else:
                print(msg, flush=True)

            params = {
                "search_query": search_query,
                "start": start_idx,
                "max_results": page_size,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            try:
                feed, page_had_rate_limit = fetch_page_with_retry(
                    session,
                    params,
                    logger,
                    retries=int(args.retries),
                    base_429_wait=float(args.base_429_wait),
                    max_429_wait=float(args.max_429_wait),
                )
            except RateLimitExhausted as e:
                any_rate_limited = True
                if pages > 1 and results:
                    logger.warning(
                        "Rate limit (429) on page %d after partial fetch (%d papers); "
                        "saving partial results and exiting with code %d.",
                        pages,
                        len(results),
                        ARXIV_EXIT_RATE_LIMIT_PARTIAL,
                    )
                    rate_limit_partial = True
                    break
                logger.warning("Rate limit (429) exhausted: %s", e)
                raise SystemExit(2) from e

            if page_had_rate_limit:
                any_rate_limited = True

            if not feed.entries:
                if pages == 1 and any_rate_limited:
                    logger.warning(
                        "First-page response is empty after rate-limit (429) error; "
                        "the 0-paper result is unreliable. Exiting with code 2."
                    )
                    sys.exit(2)
                logger.info("No entries returned; stopping.")
                break

            for entry in feed.entries:
                pub_utc = entry_published_utc_dt(entry)
                if start_utc <= pub_utc < end_utc:
                    candidates += 1
                    title = normalize_text(getattr(entry, "title", ""))
                    summary = parse_entry_summary(entry)
                    authors = parse_entry_authors(entry)
                    paper_cats = parse_entry_categories(entry)
                    arxiv_id = arxiv_id_from_entry_url(entry.id)
                    results.append(
                        Paper(
                            title=title,
                            published_utc=pub_utc,
                            arxiv_id=arxiv_id,
                            link=f"https://arxiv.org/abs/{arxiv_id}",
                            authors=authors,
                            summary=summary,
                            paper_categories=paper_cats,
                        )
                    )
                    if len(results) >= args.max_papers:
                        break

            start_idx += page_size
            time.sleep(args.sleep)

    print()
    print("============结束获取初始可下载列表==============", flush=True)
    results.sort(key=lambda p: p.published_utc, reverse=True)
    is_official_announcement = source_mode in {
        "official_listing_oai",
        "official_announcement_rss",
    }
    reported_search_query = search_query
    if is_official_announcement:
        reported_search_query = f"official listing + OAI categories: {','.join(categories)}"
        if args.query.strip():
            reported_search_query += f"; query: {build_text_clause(args.query)}"

    out_path = args.out.strip()
    if not out_path:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        if used_anchor_window and anchor_date_for_name is not None:
            out_filename = anchor_date_for_name.strftime(FILENAME_FMT)
        else:
            out_filename = datetime.now(timezone.utc).strftime(FILENAME_FMT)
        out_path = os.path.join(OUTPUT_DIR, out_filename)

    out_json_path = args.out_json.strip()
    if not out_json_path:
        if args.out.strip():
            out_json_path = os.path.splitext(out_path)[0] + ".json"
        else:
            os.makedirs(ARXIV_JSON_DIR, exist_ok=True)
            if used_anchor_window and anchor_date_for_name is not None:
                out_json_name = anchor_date_for_name.strftime(JSON_FILENAME_FMT)
            else:
                out_json_name = datetime.now(timezone.utc).strftime(JSON_FILENAME_FMT)
            out_json_path = os.path.join(ARXIV_JSON_DIR, out_json_name)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# arXiv daily papers\n\n")
        f.write(f"- Source mode: `{source_mode}`\n")
        if is_official_announcement and anchor_date_for_name is not None:
            f.write(f"- Announcement batch: **{anchor_date_for_name.isoformat()}**\n")
        f.write("- Timezone: `UTC`\n")
        f.write(
            f"- Window: **{start_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}** to **{end_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}**\n"
        )
        candidate_label = (
            "Candidates in announcement batch"
            if is_official_announcement
            else "Candidates in window"
        )
        f.write(f"- {candidate_label}: **{candidates}**\n")
        f.write(f"- Selected: **{len(results)}**\n")
        f.write(f"- search_query: `{reported_search_query}`\n\n")

        if not results:
            f.write("_No matching papers found in this window._\n")
        else:
            for i, p in enumerate(results, 1):
                pub_str = p.published_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
                f.write(f"{i}. **{p.title}**  \n")
                f.write(f"   - Published: `{pub_str}`  \n")
                f.write(f"   - arXiv: [{p.arxiv_id}]({p.link})  \n")

                if p.authors:
                    f.write(f"   - Authors: {', '.join(p.authors)}  \n")
                else:
                    f.write("   - Authors: _N/A_  \n")

                if p.summary:
                    f.write("   - Abstract:\n")
                    f.write("     <details><summary>Show</summary>\n\n")
                    f.write(f"     {p.summary}\n\n")
                    f.write("     </details>\n\n")
                else:
                    f.write("   - Abstract: _N/A_\n\n")

    os.makedirs(os.path.dirname(out_json_path) or ".", exist_ok=True)
    json_payload = {
        "source_mode": source_mode,
        "announcement_date": (
            anchor_date_for_name.isoformat()
            if is_official_announcement and anchor_date_for_name is not None
            else None
        ),
        "announcement_source_dates": announcement_source_dates,
        "timezone": "UTC",
        "window_start_utc": start_utc.isoformat(),
        "window_end_utc": end_utc.isoformat(),
        "candidates_in_window": candidates,
        "selected": len(results),
        "search_query": reported_search_query,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "papers": [
            {
                "title": p.title,
                "published_utc": p.published_utc.isoformat(),
                "arxiv_id": p.arxiv_id,
                "link": p.link,
                "authors": p.authors,
                "summary": p.summary,
                "categories": p.paper_categories,
            }
            for p in results
        ],
    }
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(json_payload, f, ensure_ascii=False, indent=2)

    # Also persist to DB (pipeline_arxiv_list table) so the JSON file can later be removed
    if used_anchor_window and anchor_date_for_name is not None:
        db_date_str = anchor_date_for_name.strftime("%Y-%m-%d")
    else:
        db_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from services.pipeline_db_service import bulk_upsert_arxiv_list
        db_papers = [
            {
                "paper_arxiv_id": p.arxiv_id,
                "title": p.title,
                "abstract_text": p.summary or "",
                "authors": p.authors or [],
                "published_utc": p.published_utc.isoformat(),
                "link": p.link,
                "categories": list(categories) if categories else [],
                "paper_categories": p.paper_categories or [],
            }
            for p in results
        ]
        bulk_upsert_arxiv_list(
            db_date_str,
            db_papers,
            replace_existing=not rate_limit_partial,
        )
        logger.info(
            "Saved %d papers to pipeline_arxiv_list DB for %s (replace=%s)",
            len(db_papers),
            db_date_str,
            not rate_limit_partial,
        )
    except Exception as _db_err:
        logger.warning("Failed to write arxiv list to DB: %s", _db_err)

    logger.info("Candidates in window: %d", candidates)
    logger.info("Selected papers     : %d", len(results))
    logger.info("Saved markdown to   : %s", out_path)
    logger.info("Saved json to       : %s", out_json_path)
    if rate_limit_partial:
        logger.warning(
            "Partial arXiv fetch due to rate limiting. "
            "Wait 15–30 minutes before re-running arxiv_search."
        )
        print("END arxiv_search.py (partial, rate limited)", flush=True)
        sys.exit(ARXIV_EXIT_RATE_LIMIT_PARTIAL)
    print("END arxiv_search.py", flush=True)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        print("FATAL ERROR:\n" + traceback.format_exc(), flush=True)
        raise
