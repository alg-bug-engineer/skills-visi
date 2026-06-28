"""Runtime network environment for the application."""

from __future__ import annotations

import os

_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


def disable_shell_proxy_env() -> None:
    """Remove shell proxy variables inherited from developer terminals.

    Terminal proxies (git/npm/pip) must not affect in-app HTTP clients such as httpx.
    """
    for key in _PROXY_ENV_KEYS:
        os.environ.pop(key, None)
