from __future__ import annotations

import logging
import os
import socket
import threading
import time
from typing import Iterable
from urllib.parse import urlsplit

import requests
import urllib3
from requests.adapters import HTTPAdapter
from requests.structures import CaseInsensitiveDict
from urllib3.util import Timeout
from urllib3.util.retry import Retry

from config.config import (
    RETRY_TOTAL,
    RETRY_BACKOFF,
    ARXIV_USER_AGENT,
    PROXIES,
    RESPECT_ENV_PROXIES,
)


logger = logging.getLogger(__name__)

# The production network currently resets TLS handshakes whose SNI names arXiv.
# Fastly's default TLS identity is reachable on the same official anycast IPs;
# the original Host header remains encrypted inside that verified TLS tunnel.
# This is deliberately restricted to arXiv GET/HEAD traffic and never disables
# certificate verification.
_ARXIV_FASTLY_TLS_HOST_DEFAULT = "s.sni-810-default.ssl.fastly.net"
_ARXIV_FASTLY_IPS_DEFAULT = (
    "151.101.3.42",
    "151.101.67.42",
    "151.101.131.42",
    "151.101.195.42",
)
_ARXIV_FALLBACK_HOSTS = frozenset({"arxiv.org", "oaipmh.arxiv.org"})
_ARXIV_FALLBACK_METHODS = frozenset({"GET", "HEAD"})
_DIRECT_CONNECT_TIMEOUT_SECONDS = 8.0
_CIRCUIT_SECONDS_DEFAULT = 6 * 60 * 60

_circuit_lock = threading.Lock()
_arxiv_circuit_open_until = 0.0


def _env_enabled(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _fallback_enabled() -> bool:
    return _env_enabled("ARXIV_VERIFIED_FASTLY_FALLBACK", True)


def _fastly_tls_host() -> str:
    value = os.environ.get(
        "ARXIV_FASTLY_TLS_HOST", _ARXIV_FASTLY_TLS_HOST_DEFAULT
    ).strip().lower()
    if not value or any(
        char not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for char in value
    ):
        raise ValueError("ARXIV_FASTLY_TLS_HOST must be a valid DNS hostname")
    return value


def _circuit_seconds() -> float:
    raw = os.environ.get("ARXIV_DIRECT_CIRCUIT_SECONDS", "").strip()
    if not raw:
        return float(_CIRCUIT_SECONDS_DEFAULT)
    try:
        return max(30.0, float(raw))
    except ValueError:
        return float(_CIRCUIT_SECONDS_DEFAULT)


def _circuit_is_open(now: float | None = None) -> bool:
    current = time.monotonic() if now is None else now
    with _circuit_lock:
        return current < _arxiv_circuit_open_until


def _open_circuit(now: float | None = None) -> None:
    global _arxiv_circuit_open_until
    current = time.monotonic() if now is None else now
    with _circuit_lock:
        _arxiv_circuit_open_until = max(
            _arxiv_circuit_open_until,
            current + _circuit_seconds(),
        )


def _reset_arxiv_circuit_for_tests() -> None:
    """Reset process-wide state; intentionally private outside regression tests."""
    global _arxiv_circuit_open_until
    with _circuit_lock:
        _arxiv_circuit_open_until = 0.0


def _cap_direct_connect_timeout(timeout):
    """Cap only the direct connect phase while preserving the caller's read limit."""
    cap = _DIRECT_CONNECT_TIMEOUT_SECONDS
    if timeout is None:
        return (cap, None)
    if isinstance(timeout, (tuple, list)) and len(timeout) == 2:
        connect, read = timeout
        if connect is None:
            connect = cap
        else:
            connect = min(float(connect), cap)
        return (connect, read)
    if isinstance(timeout, (int, float)):
        value = float(timeout)
        return (min(value, cap), value)
    return timeout


def _urllib3_timeout(timeout) -> Timeout:
    if timeout is None:
        return Timeout(connect=_DIRECT_CONNECT_TIMEOUT_SECONDS, read=None)
    if isinstance(timeout, (tuple, list)) and len(timeout) == 2:
        return Timeout(connect=timeout[0], read=timeout[1])
    if isinstance(timeout, (int, float)):
        value = float(timeout)
        return Timeout(
            connect=min(value, _DIRECT_CONNECT_TIMEOUT_SECONDS),
            read=value,
        )
    connect = getattr(
        timeout,
        "connect_timeout",
        _DIRECT_CONNECT_TIMEOUT_SECONDS,
    )
    read = getattr(timeout, "read_timeout", None)
    return Timeout(connect=connect, read=read)


def _configured_fastly_ips() -> list[str]:
    raw = os.environ.get("ARXIV_FASTLY_IPS", "")
    values = [part.strip() for part in raw.split(",") if part.strip()]
    return values or list(_ARXIV_FASTLY_IPS_DEFAULT)


def _resolved_fastly_ips(origin_host: str) -> list[str]:
    values: list[str] = []
    try:
        for result in socket.getaddrinfo(
            origin_host,
            443,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        ):
            value = result[4][0]
            if value not in values:
                values.append(value)
    except OSError as exc:
        logger.warning("arXiv DNS resolution failed for %s: %s", origin_host, exc)
    for value in _configured_fastly_ips():
        try:
            socket.inet_aton(value)
        except OSError:
            logger.warning("Ignoring invalid ARXIV_FASTLY_IPS value: %s", value)
            continue
        if value not in values:
            values.append(value)
    return values


def _certificate_options(verify) -> dict:
    if verify is False:
        raise requests.exceptions.SSLError(
            "The verified arXiv Fastly fallback refuses verify=False"
        )
    if isinstance(verify, str):
        if os.path.isdir(verify):
            return {"ca_cert_dir": verify}
        return {"ca_certs": verify}
    return {"ca_certs": requests.certs.where()}


def _request_target(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path or "/"
    return f"{path}?{parsed.query}" if parsed.query else path


def _eligible_for_verified_fallback(request) -> bool:
    parsed = urlsplit(request.url or "")
    return bool(
        parsed.scheme.lower() == "https"
        and (parsed.hostname or "").lower() in _ARXIV_FALLBACK_HOSTS
        and (request.method or "GET").upper() in _ARXIV_FALLBACK_METHODS
    )


class ArxivResilientAdapter(HTTPAdapter):
    """Direct-first adapter with a narrowly scoped, certificate-verified fallback."""

    _FALLBACK_ERRORS = (
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.SSLError,
    )

    def send(
        self,
        request,
        stream=False,
        timeout=None,
        verify=True,
        cert=None,
        proxies=None,
    ):
        if not _eligible_for_verified_fallback(request) or not _fallback_enabled():
            return super().send(
                request,
                stream=stream,
                timeout=timeout,
                verify=verify,
                cert=cert,
                proxies=proxies,
            )

        if _circuit_is_open():
            return self._send_via_verified_fastly(
                request,
                timeout=timeout,
                verify=verify,
            )

        try:
            response = super().send(
                request,
                stream=stream,
                timeout=_cap_direct_connect_timeout(timeout),
                verify=verify,
                cert=cert,
                proxies=proxies,
            )
            response.ai4papers_transport = "direct"
            return response
        except self._FALLBACK_ERRORS as direct_exc:
            _open_circuit()
            logger.warning(
                "Direct arXiv TLS failed (%s); using certificate-verified Fastly "
                "transport for this process circuit window.",
                type(direct_exc).__name__,
            )
            try:
                return self._send_via_verified_fastly(
                    request,
                    timeout=timeout,
                    verify=verify,
                )
            except Exception as fallback_exc:
                raise requests.exceptions.ConnectionError(
                    "Direct arXiv connection and verified Fastly fallback both failed"
                ) from fallback_exc

    def _send_via_verified_fastly(self, request, *, timeout, verify):
        parsed = urlsplit(request.url or "")
        origin_host = (parsed.hostname or "").lower()
        if origin_host not in _ARXIV_FALLBACK_HOSTS:
            raise requests.exceptions.InvalidURL(
                "Verified Fastly fallback only permits official arXiv hosts"
            )
        method = (request.method or "GET").upper()
        if method not in _ARXIV_FALLBACK_METHODS:
            raise requests.exceptions.InvalidURL(
                "Verified Fastly fallback only permits GET and HEAD"
            )

        tls_host = _fastly_tls_host()
        headers = dict(request.headers or {})
        headers["Host"] = origin_host
        target = _request_target(request.url)
        timeout_config = _urllib3_timeout(timeout)
        cert_options = _certificate_options(verify)
        last_error: Exception | None = None

        for ip_address in _resolved_fastly_ips(origin_host):
            pool = urllib3.HTTPSConnectionPool(
                ip_address,
                port=443,
                cert_reqs="CERT_REQUIRED",
                assert_hostname=tls_host,
                server_hostname=tls_host,
                timeout=timeout_config,
                maxsize=1,
                block=True,
                **cert_options,
            )
            try:
                raw = pool.urlopen(
                    method,
                    target,
                    body=request.body,
                    headers=headers,
                    redirect=False,
                    preload_content=False,
                    decode_content=False,
                    retries=False,
                    assert_same_host=False,
                )
            except Exception as exc:
                last_error = exc
                pool.close()
                continue

            response = requests.Response()
            response.status_code = raw.status
            response.headers = CaseInsensitiveDict(raw.headers)
            response.raw = raw
            response.reason = raw.reason
            response.url = request.url
            response.request = request
            response.connection = self
            response.ai4papers_transport = "fastly_verified"
            return response

        if last_error is not None:
            raise requests.exceptions.ConnectionError(
                "No certificate-verified Fastly address completed the arXiv request"
            ) from last_error
        raise requests.exceptions.ConnectionError(
            "No usable Fastly addresses were available for the arXiv fallback"
        )


def _apply_proxy_policy(session: requests.Session, prefer_env_proxy: bool) -> None:
    if PROXIES is not None:
        session.proxies.update(PROXIES)
    elif not (RESPECT_ENV_PROXIES or prefer_env_proxy):
        # Avoid mutating process-wide proxy environment variables.  This session
        # simply opts out, leaving unrelated services and child processes intact.
        session.trust_env = False


def _general_retry(retry_on_429: bool) -> Retry:
    status_forcelist: Iterable[int] = [500, 502, 503, 504]
    if retry_on_429:
        status_forcelist = [429, *status_forcelist]
    return Retry(
        total=RETRY_TOTAL,
        connect=RETRY_TOTAL,
        read=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )


def _no_transport_retry() -> Retry:
    # Listing/OAI/PDF callers already own their bounded application retries.
    # A second urllib3 retry loop previously multiplied one outage into tens of
    # minutes before the scheduler could record and retry the run.
    return Retry(
        total=0,
        connect=0,
        read=0,
        redirect=0,
        status=0,
        raise_on_status=False,
    )


def build_session(
    prefer_env_proxy: bool = False,
    *,
    retry_on_429: bool = True,
) -> requests.Session:
    """General session with resilient transport for official arXiv HTTPS."""
    session = requests.Session()
    general_adapter = HTTPAdapter(
        max_retries=_general_retry(retry_on_429),
        pool_connections=10,
        pool_maxsize=10,
    )
    session.mount("http://", general_adapter)
    session.mount("https://", general_adapter)

    # Longest-prefix matching keeps the special transport confined to the two
    # official origins for which the encrypted Host route was verified.
    for prefix in (
        "https://arxiv.org/",
        "https://oaipmh.arxiv.org/",
    ):
        session.mount(
            prefix,
            ArxivResilientAdapter(
                max_retries=_no_transport_retry(),
                pool_connections=10,
                pool_maxsize=10,
            ),
        )

    session.headers.update({"User-Agent": ARXIV_USER_AGENT})
    _apply_proxy_policy(session, prefer_env_proxy)
    return session


def build_arxiv_api_session(prefer_env_proxy: bool = False) -> requests.Session:
    """arXiv session — 429 is handled by bounded application-level logic."""
    return build_session(prefer_env_proxy=prefer_env_proxy, retry_on_429=False)
