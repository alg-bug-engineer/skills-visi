"""Cache Aliyun NLS access tokens."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import TYPE_CHECKING

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

if TYPE_CHECKING:
    from intersection_agent.config import Settings

logger = logging.getLogger(__name__)

_REFRESH_MARGIN_SEC = 300


class AliyunTokenManager:
    """Fetch and cache CreateToken results."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expire_at: float = 0.0

    def get_token(self) -> str:
        """Return a valid token, refreshing when near expiry."""
        with self._lock:
            now = time.time()
            if self._token and now < self._expire_at - _REFRESH_MARGIN_SEC:
                return self._token
            token, expire_time = self._fetch_token()
            self._token = token
            self._expire_at = float(expire_time)
            return token

    def _fetch_token(self) -> tuple[str, int]:
        region = self._settings.aliyun_nls_region or "cn-shanghai"
        client = AcsClient(
            self._settings.aliyun_ak_id,
            self._settings.aliyun_ak_secret,
            region,
        )
        request = CommonRequest()
        request.set_method("POST")
        request.set_domain(f"nls-meta.{region}.aliyuncs.com")
        request.set_version("2019-02-28")
        request.set_action_name("CreateToken")
        raw = client.do_action_with_exception(request)
        payload = json.loads(raw)
        token_block = payload.get("Token") or {}
        token = token_block.get("Id")
        expire_time = token_block.get("ExpireTime")
        if not token or not expire_time:
            raise RuntimeError("CreateToken response missing Token.Id or ExpireTime")
        logger.info("aliyun_token.refreshed expire_time=%s", expire_time)
        return str(token), int(expire_time)
