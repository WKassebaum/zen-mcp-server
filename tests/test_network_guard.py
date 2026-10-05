"""The unit-test network guard refuses non-loopback hosts and records each attempt (tests/network_guard.py)."""

import socket

import pytest

from tests.network_guard import block_network


def test_lookup_of_a_remote_host_is_refused_and_recorded():
    with block_network() as attempts:
        with pytest.raises(OSError):
            socket.getaddrinfo("generativelanguage.googleapis.com", 443)
    assert attempts == ["lookup generativelanguage.googleapis.com"]


def test_connect_to_a_remote_address_is_refused_and_recorded():
    with block_network() as attempts:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(OSError):
                sock.connect(("192.0.2.1", 443))  # TEST-NET-1: never routed
        finally:
            sock.close()
    assert attempts == ["connect 192.0.2.1:443"]


def test_loopback_is_allowed():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        with block_network() as attempts:
            assert socket.getaddrinfo("localhost", 80)
            client = socket.create_connection(listener.getsockname(), timeout=5)
            client.close()
        assert attempts == []
    finally:
        listener.close()


def test_the_real_functions_come_back_afterwards():
    real_getaddrinfo, real_connect = socket.getaddrinfo, socket.socket.connect
    with block_network():
        assert socket.getaddrinfo is not real_getaddrinfo
    assert socket.getaddrinfo is real_getaddrinfo
    assert socket.socket.connect is real_connect


def test_this_suite_runs_behind_the_guard():
    # conftest's autouse fixture wraps every unit test (a lookup here would be refused and then fail this test)
    assert socket.getaddrinfo.__module__ == "tests.network_guard"
    assert socket.socket.connect.__module__ == "tests.network_guard"
