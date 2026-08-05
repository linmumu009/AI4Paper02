"""Validation for user-controlled outbound HTTP targets."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


_LOCAL_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".home",
    ".lan",
)


class OutboundURLRejected(ValueError):
    pass


def _require_public_ip(value: str) -> None:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError as exc:
        raise OutboundURLRejected("模型服务地址解析结果无效") from exc
    if not address.is_global:
        raise OutboundURLRejected("模型服务地址不能指向本机、内网或保留网络")


def validate_user_llm_base_url(value: str) -> str:
    """Return a normalized public HTTPS base URL or raise a safe error."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) > 512:
        raise OutboundURLRejected("模型服务地址过长")

    parsed = urlsplit(raw)
    if parsed.scheme.lower() != "https":
        raise OutboundURLRejected("模型服务地址必须使用 HTTPS")
    if not parsed.hostname:
        raise OutboundURLRejected("模型服务地址缺少有效域名")
    if parsed.username is not None or parsed.password is not None:
        raise OutboundURLRejected("模型服务地址不能包含用户名或密码")
    if parsed.query or parsed.fragment:
        raise OutboundURLRejected("模型服务地址不能包含查询参数或片段标识")
    try:
        port = parsed.port
    except ValueError as exc:
        raise OutboundURLRejected("模型服务地址端口无效") from exc

    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(_LOCAL_HOST_SUFFIXES):
        raise OutboundURLRejected("模型服务地址不能指向本机或内部域名")

    try:
        literal = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        literal = None
    if literal is not None:
        _require_public_ip(host)
    else:
        try:
            resolved = socket.getaddrinfo(
                host,
                port or 443,
                type=socket.SOCK_STREAM,
            )
        except (OSError, UnicodeError) as exc:
            raise OutboundURLRejected("模型服务域名无法解析") from exc
        addresses = {item[4][0] for item in resolved if item and item[4]}
        if not addresses:
            raise OutboundURLRejected("模型服务域名没有可用地址")
        for address in addresses:
            _require_public_ip(address)

    normalized_host = f"[{host}]" if literal and literal.version == 6 else host
    port_suffix = f":{port}" if port is not None else ""
    path = parsed.path.rstrip("/")
    return f"https://{normalized_host}{port_suffix}{path}"
