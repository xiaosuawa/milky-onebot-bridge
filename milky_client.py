"""Milky WS 事件接收 + HTTP API 调用."""
import asyncio
import json
import logging
import traceback

import httpx
import websockets.asyncio.client as ws_client

from models import MilkyEvent

logger = logging.getLogger("bridge.milky")


class MilkyClient:
    def __init__(self, ws_url: str, http_url: str, access_token: str = ""):
        self.ws_url = ws_url
        self.http_url = http_url.rstrip("/")
        self.access_token = access_token
        self._http: httpx.AsyncClient | None = None
        self._ws: ws_client.WebSocketClientProtocol | None = None
        self._event_queue: asyncio.Queue[MilkyEvent] = asyncio.Queue()

    async def __aenter__(self):
        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        self._http = httpx.AsyncClient(base_url=self.http_url, headers=headers, timeout=30.0)
        logger.info("Milky HTTP 客户端初始化: %s", self.http_url)
        return self

    async def __aexit__(self, *args):
        if self._http:
            await self._http.aclose()

    async def connect_ws(self):
        """连接 Milky WebSocket."""
        self._ws = await ws_client.connect(self.ws_url)
        asyncio.create_task(self._ws_recv_loop())

    async def _ws_recv_loop(self):
        """持续接收 WS 事件, 解析放入队列. 断连自动重试."""
        retry_delay = 1
        while True:
            try:
                logger.info("Milky WS 已连接: %s", self.ws_url)
                async for raw in self._ws:
                    retry_delay = 1
                    try:
                        data = json.loads(raw)
                        logger.debug("Milky 事件: %s", data.get("event_type", "?"))
                        self._event_queue.put_nowait(MilkyEvent(
                            event_type=data["event_type"],
                            time=data["time"],
                            self_id=data["self_id"],
                            data=data["data"],
                        ))
                    except Exception:
                        logger.error("Milky WS 消息解析失败:\n%s", traceback.format_exc())
            except asyncio.CancelledError:
                return
            except Exception:
                logger.error("Milky WS 断连, %ss 后重试:\n%s", retry_delay, traceback.format_exc())
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)
                try:
                    self._ws = await ws_client.connect(self.ws_url)
                except Exception:
                    pass

    async def events(self):
        """异步迭代器: 产出 MilkyEvent."""
        while True:
            yield await self._event_queue.get()

    async def call_api(self, action: str, params: dict) -> dict:
        """调用 Milky HTTP API, 返回 JSON 响应体."""
        url = f"/api/{action}"
        # 日志：message 字段只打印段类型
        logged = {}
        for k, v in params.items():
            if k == "message" and isinstance(v, list):
                logged[k] = [s.get("type", "?") for s in v]
            else:
                logged[k] = v
        logger.info("Milky API: POST %s %s", url, logged)
        resp = await self._http.post(url, json=params)
        resp.raise_for_status()
        result = resp.json()
        return result
