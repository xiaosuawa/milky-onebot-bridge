"""Onebot v11 HTTP 服务端 — 提供 API 给调用方 + 推送事件."""
import asyncio
import logging
import traceback

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
import uvicorn

from milky_client import MilkyClient
from api_mapping import map_api_call, wrap_response
from event_mapping import convert_event, strip_first_at_after_reply

logger = logging.getLogger("bridge.onebot")


class OnebotServer:
    def __init__(
        self,
        listen_host: str,
        listen_port: int,
        access_token: str,
        event_push_url: str,
        skip_self_message: bool,
        milky: MilkyClient,
        strip_at_after_reply: bool = False,
    ):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.access_token = access_token
        self.event_push_url = event_push_url.rstrip("/")
        self.skip_self_message = skip_self_message
        self.strip_at_after_reply = strip_at_after_reply
        self.milky = milky
        self._self_id = 0  # 从 WS 事件里缓存，供历史消息路径判断 is_self_send 用

    async def run(self):
        """连 Milky WS + 启动 HTTP 服务端 + 后台推送事件."""
        logger.info("连接 Milky WebSocket: %s", self.milky.ws_url)
        await self.milky.connect_ws()
        logger.info("Milky WebSocket 已连接")

        app = Starlette(routes=[
            Route("/", endpoint=self._handle_root, methods=["GET"]),
            Route("/", endpoint=self._handle_event_and_api, methods=["POST"]),
            Route("/{action:path}", endpoint=self._handle_event_and_api, methods=["POST"]),
        ])

        # 后台: Milky 事件 → Onebot 格式 → POST 给调用方
        asyncio.create_task(self._event_push_loop())

        logger.info("Onebot HTTP 服务启动: http://%s:%s", self.listen_host, self.listen_port)
        config = uvicorn.Config(app, host=self.listen_host, port=self.listen_port, log_level="info")
        await uvicorn.Server(config).serve()

    async def _handle_root(self, request: Request):
        """GET / — 健康检查 + 彩蛋."""
        return PlainTextResponse(
            "🥛 Milky-OneBot Bridge is running!\n"
            "   协议翻译中... 一头奶牛正在搬运你的消息 🐄\n"
            "   Milky ←→ Onebot v11\n"
        )

    async def _handle_event_and_api(self, request: Request):
        """统一处理调用方发来的请求: API 调用和事件上报用同一个端点."""
        try:
            body = await request.json() or {}
        except Exception:
            logger.warning("无法解析请求 JSON: %s %s", request.method, request.url.path)
            return JSONResponse({"status": "failed", "retcode": 1400}, status_code=400)

        # action 优先从 body 取，没有则从 URL 路径取
        action = body.get("action", "")
        params = body.get("params", {})
        echo = body.get("echo")

        if not action:
            # 路径式调用: POST /get_group_info, body 里只有 params 没有 action
            path_action = request.path_params.get("action", "").strip("/")
            if path_action:
                action = path_action
                params = body  # body 整体就是 params

        if not action:
            logger.warning("请求缺少 action: url=%s body=%s", request.url.path, body)
            return JSONResponse({"status": "failed", "retcode": 1400, "wording": "missing action"}, status_code=400)

        # 调用 Milky API
        milky_action, milky_params = map_api_call(action, params)

        try:
            result = await self.milky.call_api(milky_action, milky_params)
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500] if e.response.text else "(empty)"
            logger.error(
                "Milky API 返回错误: %s → HTTP %s\n请求: %s\n响应体: %s",
                milky_action, e.response.status_code,
                {k: v for k, v in milky_params.items()},
                body,
            )
            return JSONResponse({
                "status": "failed", "retcode": e.response.status_code,
                "wording": body,
                "echo": echo,
            })
        except Exception as e:
            logger.error(
                "Milky API 调用异常: %s → %s\n请求: %s\n异常: %s",
                action, milky_action,
                {k: v for k, v in milky_params.items()},
                e,
            )
            return JSONResponse({
                "status": "failed", "retcode": 1400, "wording": str(e),
                "echo": echo,
            })

        # 检查 Milky 响应
        code = result.get("code")
        if code != 0 and code is not None:
            logger.warning("Milky 返回错误: %s → code=%s msg=%s", milky_action, code, result.get("msg", ""))
            return JSONResponse({
                "status": "failed",
                "retcode": code,
                "wording": result.get("msg", ""),
                "echo": echo,
            })

        data = result.get("data", result)
        wrapped = wrap_response(milky_action, data, milky_params)
        await self._enrich_response(milky_action, wrapped)

        return JSONResponse({
            "status": "ok", "retcode": 0,
            "data": wrapped, "echo": echo,
        })

    async def _event_push_loop(self):
        """消费 Milky 事件队列, 转为 Onebot 格式 POST 给调用方."""
        logger.info("事件推送循环启动, 目标: %s (skip_self=%s)",
                     self.event_push_url, self.skip_self_message)
        async with httpx.AsyncClient(timeout=10) as client:
            async for event in self.milky.events():
                self._self_id = event.self_id
                ob = convert_event(event)
                if ob is None:
                    continue
                # 删除回复段后的第一个 at 段 (配置开启时)
                if self.strip_at_after_reply and ob.post_type == "message":
                    strip_first_at_after_reply(ob)
                # 忽略自己的消息
                if self.skip_self_message and event.event_type == "message_receive":
                    sender_id = event.data.get("sender_id", 0) if isinstance(event.data, dict) else 0
                    if sender_id == event.self_id:
                        logger.debug("跳过自身消息: self=%s sender=%s", event.self_id, sender_id)
                        continue
                # 富化消息段: 补齐缺 url 的文件/图片/语音/视频下载链接
                if event.event_type == "message_receive" and ob.post_type == "message":
                    data = event.data if isinstance(event.data, dict) else {}
                    await self._enrich_segments(
                        ob.extra.get("message", []),
                        data.get("message_scene", ""),
                        data.get("peer_id", 0),
                        data.get("sender_id", 0),
                        event.self_id,
                    )
                logger.info("推送事件: %s → %s", event.event_type, self.event_push_url)
                try:
                    resp = await client.post(
                        self.event_push_url,
                        json=ob.to_dict(),
                        headers={"Authorization": f"Bearer {self.access_token}"} if self.access_token else {},
                    )
                    logger.debug("事件推送响应: status=%s", resp.status_code)
                except Exception:
                    logger.error("事件推送失败:\n%s", traceback.format_exc())

    async def _enrich_segments(self, cqs, scene, peer_id, sender_id, self_id):
        """对缺 url 的段调用 Milky API 补齐下载链接 (原地修改 cqs).

        Milky 文件段本身不带 URL，image/record/video 的 temp_url 也可能为空，
        这里按段类型调对应接口把 url 抹平，失败则保持空串降级，不影响消息推送.
        """
        for seg in cqs:
            if not isinstance(seg, dict):
                continue
            d = seg.get("data")
            if not isinstance(d, dict):
                continue
            t = seg.get("type")
            if t == "file" and not d.get("url"):
                d["url"] = await self._resolve_file_url(scene, peer_id, d, sender_id, self_id)
            elif t in ("image", "record", "video") and not d.get("url") and d.get("resource_id"):
                url = await self._resolve_resource_url(d["resource_id"])
                if url:
                    d["url"] = url
                    d["file"] = url

    async def _resolve_file_url(self, scene, peer_id, d, sender_id, self_id):
        file_id = d.get("file_id", "")
        if not file_id:
            return ""
        # 文件下载需明确群/私聊场景；合并转发消息无 peer 信息(无 group_id/user_id)，无法定位
        if not peer_id or scene not in ("group", "friend", "temp"):
            return ""
        try:
            if scene == "group":
                action, params = "get_group_file_download_url", {
                    "group_id": peer_id, "file_id": file_id,
                }
            else:
                action, params = "get_private_file_download_url", {
                    "user_id": peer_id,
                    "file_id": file_id,
                    "file_hash": d.get("file_hash", ""),
                    "is_self_send": bool(self_id and sender_id == self_id),
                }
            result = await self.milky.call_api(action, params)
            data = result.get("data") or {}
            return data.get("download_url", "")
        except Exception:
            logger.warning("获取文件下载链接失败: scene=%s file_id=%s", scene, file_id, exc_info=True)
            return ""

    async def _resolve_resource_url(self, resource_id):
        try:
            result = await self.milky.call_api("get_resource_temp_url", {"resource_id": resource_id})
            data = result.get("data") or {}
            return data.get("url", "")
        except Exception:
            logger.warning("获取资源临时链接失败: resource_id=%s", resource_id, exc_info=True)
            return ""

    async def _enrich_message_dict(self, msg):
        if not isinstance(msg, dict):
            return
        await self._enrich_segments(
            msg.get("message", []),
            msg.get("message_scene", ""),
            msg.get("peer_id", 0),
            msg.get("sender_id", 0),
            self._self_id,
        )

    async def _enrich_response(self, action, wrapped):
        """产出消息段的响应同样需要补齐 url (file/image/record/video).

        覆盖 get_message / get_history_messages / get_forwarded_messages.
        """
        if action == "get_message":
            await self._enrich_message_dict(wrapped)
        elif action in ("get_history_messages", "get_forwarded_messages"):
            for m in wrapped.get("messages", []):
                await self._enrich_message_dict(m)
