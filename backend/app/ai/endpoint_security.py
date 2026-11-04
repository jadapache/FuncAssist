"""Validation for externally hosted provider endpoints."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def _blocked_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


def is_loopback_or_private_host(hostname: str) -> bool:
    host = hostname.strip().lower().strip("[]")
    if host in {"localhost", "::1", "0.0.0.0"} or host.endswith((".local", ".internal")):
        return True
    try:
        return _blocked_ip(host)
    except ValueError:
        pass
    try:
        return any(_blocked_ip(info[4][0]) for info in socket.getaddrinfo(host, None))
    except (socket.gaierror, socket.herror, OSError, ValueError):
        return False


def validate_remote_endpoint_url(url_string: str, allow_http: bool = False) -> tuple[bool, str | None]:
    trimmed = (url_string or "").strip()
    if not trimmed:
        return False, "La URL del endpoint remoto es obligatoria."
    try:
        parsed = urlparse(trimmed)
    except Exception:
        return False, "Formato de URL inválido."
    if parsed.scheme.lower() != "https" and not (allow_http and parsed.scheme.lower() == "http"):
        return False, "El endpoint remoto debe utilizar protocolo HTTPS."
    if not parsed.hostname or is_loopback_or_private_host(parsed.hostname):
        return False, "Endpoints locales y redes privadas no están permitidos."
    return True, None
