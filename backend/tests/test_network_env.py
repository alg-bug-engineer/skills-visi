"""Tests for runtime network environment helpers."""

from __future__ import annotations

import os

from intersection_agent.network_env import disable_shell_proxy_env


def test_disable_shell_proxy_env_clears_proxy_variables(monkeypatch):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:7897")
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:7897")
    monkeypatch.setenv("all_proxy", "socks5://127.0.0.1:7897")
    monkeypatch.setenv("NO_PROXY", "localhost")

    disable_shell_proxy_env()

    for key in (
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "NO_PROXY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
    ):
        assert key not in os.environ
