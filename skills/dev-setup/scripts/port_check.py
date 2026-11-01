"""Checks local ports for the review app (reference/review-app.md).

Run with any Python 3 (stdlib only), on Windows, Linux or macOS:

    S="$HOME/.claude/skills/dev-setup/scripts"
    python "$S/port_check.py" busy <port>    # exit 0 = busy, 1 = free
    python "$S/port_check.py" free           # prints a port free on both addresses

A port is busy when something answers on 127.0.0.1 or on ::1. Vite on Node 17+ listens
on `localhost` as ::1 only, so a check of 127.0.0.1 alone saw a running dev server as a
free port (claude-config#52).
"""

import socket
import sys

IPV4 = (socket.AF_INET, "127.0.0.1")
IPV6 = (socket.AF_INET6, "::1")
TIMEOUT_SECONDS = 0.5
FREE_PORT_ATTEMPTS = 20


def can_bind(family: int, host: str, port: int) -> bool:
    """True when host:port can be bound now (port 0: any port)."""
    try:
        with socket.socket(family, socket.SOCK_STREAM) as candidate:
            candidate.bind((host, port))
            return True
    except OSError:
        return False


def loopbacks() -> list[tuple[int, str]]:
    """The loopback addresses this machine has; ::1 only where IPv6 is on."""
    # Without IPv6 nothing can listen on ::1, so there is nothing to check there.
    return [IPV4, IPV6] if can_bind(*IPV6, 0) else [IPV4]


def answers(family: int, host: str, port: int) -> bool:
    """True when something accepts a connection on host:port."""
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        probe.settimeout(TIMEOUT_SECONDS)
        return probe.connect_ex((host, port)) == 0


def is_busy(port: int) -> bool:
    """True when the port answers on any loopback address."""
    return any(answers(family, host, port) for family, host in loopbacks())


def free_port() -> int:
    """A port that is free on every loopback address."""
    addresses = loopbacks()
    for _ in range(FREE_PORT_ATTEMPTS):
        with socket.socket(IPV4[0], socket.SOCK_STREAM) as first:
            first.bind((IPV4[1], 0))
            port = first.getsockname()[1]
        if all(can_bind(family, host, port) for family, host in addresses):
            return port
    raise RuntimeError(f"no port free on every loopback in {FREE_PORT_ATTEMPTS} tries")


def main(argv: list[str]) -> int:
    """Runs the command in argv; returns the exit code."""
    if len(argv) == 2 and argv[0] == "busy" and argv[1].isdigit():
        return 0 if is_busy(int(argv[1])) else 1
    if argv == ["free"]:
        print(free_port())
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
