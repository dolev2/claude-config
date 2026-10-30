"""port_check.py: busy on 127.0.0.1 or ::1, and a free port is free on both."""

import importlib.util
import socket
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "port_check.py"
spec = importlib.util.spec_from_file_location("port_check", SCRIPT)
port_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(port_check)

needs_ipv6 = pytest.mark.skipif(
    port_check.IPV6 not in port_check.loopbacks(), reason="no IPv6 loopback here"
)


def listen_on(family, host, port=0):
    """A listening socket on host; the caller closes it."""
    server = socket.socket(family, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()
    return server


def test_port_listening_on_ipv4_is_busy():
    with listen_on(*port_check.IPV4) as server:
        assert port_check.is_busy(server.getsockname()[1])


@needs_ipv6
def test_port_listening_only_on_ipv6_is_busy():
    with listen_on(*port_check.IPV6) as server:
        port = server.getsockname()[1]
        assert not port_check.answers(*port_check.IPV4, port)
        assert port_check.is_busy(port)


def test_closed_port_is_free():
    with listen_on(*port_check.IPV4) as server:
        port = server.getsockname()[1]
    assert not port_check.is_busy(port)


def test_free_port_binds_on_every_loopback():
    port = port_check.free_port()
    for family, host in port_check.loopbacks():
        assert port_check.can_bind(family, host, port)


@needs_ipv6
def test_free_port_skips_a_port_taken_on_ipv6(monkeypatch):
    with listen_on(*port_check.IPV6) as taken:
        taken_port = taken.getsockname()[1]
        offered = iter([taken_port, 0])
        real_socket = socket.socket

        class FirstBindOffers(real_socket):
            def bind(self, address):
                if address == (port_check.IPV4[1], 0):
                    address = (address[0], next(offered))
                super().bind(address)

        monkeypatch.setattr(port_check.socket, "socket", FirstBindOffers)
        assert port_check.free_port() != taken_port


def test_cli_exit_codes(capsys):
    with listen_on(*port_check.IPV4) as server:
        assert port_check.main(["busy", str(server.getsockname()[1])]) == 0
    assert port_check.main(["free"]) == 0
    assert capsys.readouterr().out.strip().isdigit()
    assert port_check.main(["nonsense"]) == 2
