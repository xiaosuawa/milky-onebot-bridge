"""消息 ID 编解码 + 消息段双向转换."""


# ============================================================
# message_id 编解码
# scene(1bit) | peer_id(64bit) | message_seq(64bit)
# ============================================================

def pack_msg_id(scene: str, peer_id: int, seq: int) -> int:
    """可变长度编码.
    布局 (MSB→LSB): [seq(剩余)] [peer(n)] [s(1)] [n(7)]
    只记 peer 的位宽, seq 占满高位剩余部分, 无需额外长度.
    """
    s = 0 if scene == "friend" else 1
    n = peer_id.bit_length()
    header = (s << 7) | n                          # s(1) | n(7)
    result = (peer_id << 8) | header               # peer(n) | header
    result = (seq << (n + 8)) | result             # seq | peer | header
    return result


def unpack_msg_id(msg_id: int) -> tuple[str, int, int]:
    """可变长度解码."""
    header = msg_id & 0xFF
    n = header & 0x7F
    s = (header >> 7) & 1
    msg_id >>= 8
    peer_id = msg_id & ((1 << n) - 1) if n else 0
    seq = msg_id >> n                              # 剩余位 = seq
    scene = "friend" if s == 0 else "group"
    return scene, peer_id, seq


# ============================================================
# Milky → Onebot 段转换 (入站)
# ============================================================

def milky_to_cq(seg: "MilkySegment", scene: str = "", peer_id: int = 0) -> "CQSegment":
    from models import CQSegment

    d = seg.data
    match seg.type:
        case "text":
            return CQSegment("text", {"text": d.get("text", "")})
        case "mention":
            # OneBot at.name 虽 deprecated，但 schema 标为 required；Milky v1.2 起 mention 带 name
            return CQSegment("at", {
                "qq": str(d.get("user_id", "")),
                "name": d.get("name", ""),
            })
        case "mention_all":
            return CQSegment("at", {"qq": "all"})
        case "reply":
            # 编码为完整 message_id，这样调用方之后可以用它调 API
            seq = d.get("message_seq", 0)
            if scene:
                mid = pack_msg_id(scene, peer_id, seq)
            else:
                mid = seq
            return CQSegment("reply", {"id": str(mid)})
        case "image":
            url = d.get("temp_url", "")
            # OneBot image 必填 file/filename/url/summary/subType；Milky 段无 file_name，用 url 末段兜底
            sub_type = 1 if d.get("sub_type") == "sticker" else 0
            return CQSegment("image", {
                "file": url, "url": url,
                "filename": d.get("file_name", url.rsplit("/", 1)[-1] if url else ""),
                "summary": d.get("summary", ""),
                "subType": sub_type,
                "resource_id": d.get("resource_id", ""),
            })
        case "record":
            url = d.get("temp_url", "")
            return CQSegment("record", {
                "file": url, "url": url,
                "resource_id": d.get("resource_id", ""),
            })
        case "video":
            url = d.get("temp_url", "")
            return CQSegment("video", {
                "file": url, "url": url,
                "resource_id": d.get("resource_id", ""),
            })
        case "forward":
            return CQSegment("forward", {"id": d.get("forward_id", "")})
        case "file":
            # Milky 文件段无 URL (区别于 image/record/video 的 temp_url)；本函数是同步的，
            # url 留空，由 onebot_server 的 async 补齐入口按 file_id 调下载链接接口填回。
            return CQSegment("file", {
                "file_name": d.get("file_name", ""),
                "file_id": d.get("file_id", ""),
                "file_hash": d.get("file_hash", ""),
                "file_size": d.get("file_size", 0),
                "url": "",
            })
        case "face":
            return CQSegment("face", {
                "id": str(d.get("face_id", "")),
                "large": d.get("is_large", False),
            })
        case "market_face":
            # Lagrange 用独立的 mface 段承载商城表情，face.id 只接受纯数字，不能混用
            return CQSegment("mface", {
                "emoji_package_id": d.get("emoji_package_id", 0),
                "emoji_id": d.get("emoji_id", ""),
                "key": d.get("key", ""),
                "summary": d.get("summary", ""),
                "url": d.get("url", ""),
            })
        case "xml":
            return CQSegment("xml", {"data": d.get("xml_payload", "")})
        case "light_app":
            return CQSegment("json", {"data": d.get("json_payload", str(d))})
        case "markdown":
            return CQSegment("markdown", {"content": d.get("content", "")})
        case _:
            return CQSegment("text", {"text": f"[不支持: {seg.type}]"})


# ============================================================
# Onebot → Milky 段转换 (出站)
# 严格按 Milky 协议规范 v1.2 的 required 字段
# ============================================================

def cq_to_milky(seg: dict) -> "MilkyOutgoingSegment":
    from models import MilkyOutgoingSegment as MS
    import logging
    _log = logging.getLogger("bridge.translator")

    typ = seg.get("type", "")
    data = seg.get("data", {})

    _log.debug("CQ→Milky: type=%s data_keys=%s", typ, list(data.keys()))

    match typ:
        # --- 双向支持 ---
        case "text":
            return MS("text", {"text": data.get("text", "")})

        case "at":
            qq = str(data.get("qq", ""))
            if qq == "all":
                return MS("mention_all", {})
            try:
                return MS("mention", {"user_id": int(qq)})
            except (ValueError, TypeError):
                return MS("text", {"text": f"@{qq}"})

        case "reply":
            # 所有从 OB 来的 message_id 都是桥编码的，统一解码
            _, _, seq = unpack_msg_id(int(data.get("id", "0")))
            return MS("reply", {"message_seq": seq})

        case "image":
            return MS("image", {
                "uri": data.get("file", ""),
                "summary": None,
                "sub_type": "normal",
            })

        case "record":
            return MS("record", {"uri": data.get("file", "")})

        case "video":
            return MS("video", {
                "uri": data.get("file", ""),
                "thumb_uri": None,
            })

        case "forward":
            # 调用方发的是 {"id": "..."} (引用), Milky 需要 {"messages": [...]} (构造)
            return MS("forward", {
                "messages": data.get("messages", []),
                "title": data.get("title"),
                "preview": data.get("preview"),
                "summary": data.get("summary"),
                "prompt": data.get("prompt"),
            })

        # --- 降级为 text ---
        case "markdown":
            return MS("text", {"text": data.get("content", "")})
        case "keyboard":
            return MS("text", {"text": f"[keyboard]"})
        case "json":
            # v1.2+ light_app 段
            return MS("light_app", {
                "json_payload": data.get("data", ""),
                "app_name": data.get("app_name", ""),
            })
        case "xml":
            return MS("text", {"text": data.get("data", "")})
        case "face":
            return MS("face", {
                "face_id": str(data.get("id", "")),
                "is_large": False,
            })
        case "poke":
            return MS("text", {"text": "[戳一戳]"})
        case "mface":
            # Milky 发送段无 market_face，降级为文本
            return MS("text", {"text": f"[商城表情:{data.get('emoji_id','')}]"})
        case "share":
            return MS("text", {"text": f"[分享:{data.get('title','')}] {data.get('url','')}"})
        case "music":
            return MS("text", {"text": f"[音乐:{data.get('type','')}/{data.get('id','')}]"})
        case "contact":
            return MS("text", {"text": f"[推荐:{data.get('type','')}/{data.get('id','')}]"})
        case "location":
            return MS("text", {"text": f"[位置:{data.get('lat','')},{data.get('lon','')}]"})
        case "rps" | "dice" | "dict" | "shake" | "anonymous":
            # 猜拳/骰子等随机段：Milky 发送段无对应类型，降级为友好文本
            label = {"rps": "猜拳", "dice": "骰子", "dict": "骰子", "shake": "抖动", "anonymous": "匿名"}.get(typ, typ)
            return MS("text", {"text": f"[{label}]"})
        case "node":
            # 合并转发节点不应出现在普通消息中
            return MS("text", {"text": "[转发节点]"})

        case _:
            return MS("text", {"text": f"[不支持:{typ}]"})
