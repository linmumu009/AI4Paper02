import os
import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from config.config import (
    RETRY_TOTAL,
    RETRY_BACKOFF,
    ARXIV_USER_AGENT,
    PROXIES,
    RESPECT_ENV_PROXIES,
)


def _apply_proxy_policy(session: requests.Session, prefer_env_proxy: bool) -> None:
    if PROXIES is not None:
        session.proxies.update(PROXIES)
    elif not (RESPECT_ENV_PROXIES or prefer_env_proxy):
        for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
            os.environ.pop(k, None)


def build_session(
    prefer_env_proxy: bool = False,
    *,
    retry_on_429: bool = True,
) -> requests.Session:
    """General HTTP session (PDF download, etc.)."""
    s = requests.Session()
    status_forcelist = [500, 502, 503, 504]
    if retry_on_429:
        status_forcelist = [429] + status_forcelist
    retry = Retry(
        total=RETRY_TOTAL,
        connect=RETRY_TOTAL,
        read=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({"User-Agent": ARXIV_USER_AGENT})
    _apply_proxy_policy(s, prefer_env_proxy)
    return s


def build_arxiv_api_session(prefer_env_proxy: bool = False) -> requests.Session:
    """arXiv export API session — 429 handled in application code, not urllib3."""
    return build_session(prefer_env_proxy=prefer_env_proxy, retry_on_429=False)
