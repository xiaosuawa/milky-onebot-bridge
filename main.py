"""Milky-OneBot protocol bridge entry point."""
import asyncio
import logging
import shutil
from pathlib import Path

import yaml

from milky_client import MilkyClient
from onebot_server import OnebotServer

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
CONFIG_TEMPLATE = BASE_DIR / "config.example.yaml"

# 日志格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("bridge.translator").setLevel(logging.DEBUG)

logger = logging.getLogger("bridge")


def load_config() -> dict:
    """读取 config.yaml; 首次运行时从 config.example.yaml 生成."""
    if not CONFIG_PATH.exists():
        if not CONFIG_TEMPLATE.exists():
            raise FileNotFoundError(
                f"缺少 {CONFIG_PATH.name}, 且找不到模板 {CONFIG_TEMPLATE.name}"
            )
        shutil.copyfile(CONFIG_TEMPLATE, CONFIG_PATH)
        logger.info("已从模板生成配置文件: %s", CONFIG_PATH)

    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["bridge"]


async def main():
    cfg = load_config()

    milky = MilkyClient(
        ws_url=cfg["milky"]["ws_url"],
        http_url=cfg["milky"]["http_url"],
        access_token=cfg["milky"]["access_token"],
    )

    extensions = cfg.get("extensions", {})

    server = OnebotServer(
        listen_host=cfg["onebot"]["listen_host"],
        listen_port=cfg["onebot"]["listen_port"],
        access_token=cfg["onebot"]["access_token"],
        event_push_url=cfg["onebot"]["event_push_url"],
        skip_self_message=cfg.get("skip_self_message", True),
        strip_at_after_reply=extensions.get("strip_at_after_reply", False),
        milky=milky,
    )

    async with milky:
        await server.run()


if __name__ == "__main__":
    asyncio.run(main())
