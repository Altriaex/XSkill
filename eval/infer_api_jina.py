"""Run XSkill with a process-local DNS override for Jina Reader."""

import runpy
import socket
from pathlib import Path

_original_getaddrinfo = socket.getaddrinfo


def resolve_with_jina_override(host, port, *args, **kwargs):
    """Resolve only Jina Reader through the previously verified address."""
    if host == "r.jina.ai":
        host = "104.26.11.242"
    return _original_getaddrinfo(host, port, *args, **kwargs)


if __name__ == "__main__":
    # Apply the override before importing the original inference entry point.
    socket.getaddrinfo = resolve_with_jina_override
    try:
        runpy.run_path(
            str(Path(__file__).with_name("infer_api.py")),
            run_name="__main__",
        )
    finally:
        socket.getaddrinfo = _original_getaddrinfo
