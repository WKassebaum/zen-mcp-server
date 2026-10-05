"""Keep unit tests off the network.

An unmocked provider call in a unit test reaches the real API with the dummy key. On most networks it fails at once,
and the test usually still passes because its assertions accept the error path. On others the connection stalls and
the run never finishes. The guard refuses every lookup or connection to a non-loopback host and records it, so
tests/conftest.py can fail the test that tried.

It also turns proxies off: through a proxy on 127.0.0.1 (Proxyman, Charles, a corporate agent) the remote host is
never looked up here, and the only connection the guard would see is the allowed loopback one.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Iterator
from contextlib import contextmanager

_LOOPBACK_NAMES = {"localhost", "localhost.localdomain"}
_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
# A non-empty no_proxy also stops urllib.request.getproxies() (which httpx and requests use) from falling back to the
# macOS system proxy settings, and "*" bypasses every proxy.
_NO_PROXY_VARS = ("NO_PROXY", "no_proxy")


def _is_loopback(host) -> bool:
    if host is None:  # getaddrinfo(None, port) resolves to a local address
        return True
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    host = str(host)
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


@contextmanager
def block_network() -> Iterator[list[str]]:
    """Refuse non-loopback lookups and connections in every thread; yield the list of refused attempts.

    Proxy variables are removed, and no_proxy set to "*", for the duration.
    """
    attempts: list[str] = []
    saved_env = {name: os.environ.get(name) for name in _PROXY_VARS + _NO_PROXY_VARS}
    real_getaddrinfo = socket.getaddrinfo
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def getaddrinfo(host, *args, **kwargs):
        if not _is_loopback(host):
            attempts.append(f"lookup {host}")
            raise socket.gaierror(socket.EAI_NONAME, f"network blocked in unit tests: {host}")
        return real_getaddrinfo(host, *args, **kwargs)

    def refuse_remote(sock, address) -> None:
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address[0]):
            attempts.append(f"connect {address[0]}:{address[1]}")
            raise ConnectionRefusedError(f"network blocked in unit tests: {address[0]}")

    def connect(self, address):
        refuse_remote(self, address)
        return real_connect(self, address)

    def connect_ex(self, address):
        refuse_remote(self, address)
        return real_connect_ex(self, address)

    for name in _PROXY_VARS:
        os.environ.pop(name, None)
    for name in _NO_PROXY_VARS:
        os.environ[name] = "*"
    socket.getaddrinfo = getaddrinfo
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    try:
        yield attempts
    finally:
        socket.getaddrinfo = real_getaddrinfo
        socket.socket.connect = real_connect
        socket.socket.connect_ex = real_connect_ex
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
