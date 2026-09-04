"""Small fail-closed HTTP client for tenant-configured WWS endpoints."""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import ssl
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit


class UnsafeOutboundUrl(ValueError):
    """Raised when an outbound destination is not a public HTTPS endpoint."""


def _resolve_public_address(hostname: str, port: int) -> str:
    """Resolve once, reject mixed/private answers, and return a pinned address."""
    try:
        answers = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise UnsafeOutboundUrl('WWS host could not be resolved') from exc

    addresses = {answer[4][0] for answer in answers}
    if not addresses:
        raise UnsafeOutboundUrl('WWS host did not resolve to an address')

    parsed_addresses = [ipaddress.ip_address(value) for value in addresses]
    if any(not address.is_global for address in parsed_addresses):
        raise UnsafeOutboundUrl('WWS host resolves to a non-public address')

    # Deterministic selection makes tests and audit logs reproducible. The
    # socket connects to this exact address, closing the DNS-rebinding window.
    return str(sorted(parsed_addresses, key=lambda item: (item.version, int(item)))[0])


def fetch_public_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10,
    max_bytes: int = 2 * 1024 * 1024,
) -> Any:
    """Fetch bounded JSON from a public HTTPS URL without following redirects."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != 'https'
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise UnsafeOutboundUrl('Only credential-free HTTPS URLs are allowed')

    hostname = parsed.hostname.rstrip('.').lower()
    if hostname == 'localhost' or hostname.endswith(('.localhost', '.local')):
        raise UnsafeOutboundUrl('Local WWS hosts are not allowed')

    port = parsed.port or 443
    pinned_address = _resolve_public_address(hostname, port)

    query = parsed.query
    if params:
        encoded = urlencode(params, doseq=True)
        query = f'{query}&{encoded}' if query else encoded
    target = urlunsplit(('', '', parsed.path or '/', query, ''))

    raw_socket = socket.create_connection((pinned_address, port), timeout=timeout)
    connection = http.client.HTTPSConnection(
        hostname,
        port=port,
        timeout=timeout,
        context=ssl.create_default_context(),
    )
    try:
        connection.sock = connection._context.wrap_socket(  # noqa: SLF001
            raw_socket,
            server_hostname=hostname,
        )
        request_headers = {
            'Accept': 'application/json',
            'Connection': 'close',
            'Host': hostname if port == 443 else f'{hostname}:{port}',
            **(headers or {}),
        }
        connection.request('GET', target, headers=request_headers)
        response = connection.getresponse()

        if 300 <= response.status < 400:
            raise UnsafeOutboundUrl('WWS redirects are not allowed')
        if response.status < 200 or response.status >= 300:
            raise ValueError(f'WWS returned HTTP {response.status}')

        content_length = response.getheader('Content-Length')
        if content_length is not None:
            try:
                if int(content_length) > max_bytes:
                    raise ValueError('WWS response exceeds the size limit')
            except ValueError as exc:
                if str(exc) == 'WWS response exceeds the size limit':
                    raise
                raise ValueError('WWS returned an invalid Content-Length') from exc

        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError('WWS response exceeds the size limit')
        return json.loads(body.decode('utf-8'))
    finally:
        connection.close()

