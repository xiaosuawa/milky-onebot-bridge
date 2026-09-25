"""Onebot API → Milky API 路由映射."""
from translator import unpack_msg_id, cq_to_milky, pack_msg_id, milky_to_cq


def _coerce_numbers(params: dict) -> dict:
    """调用方有时把数字字段传成字符串，统一转成 int."""
    result = {}
    for k, v in params.items():
        if isinstance(v, str) and v.isdigit():
            result[k] = int(v)
        elif isinstance(v, str) and v.lstrip("-").isdigit():
            result[k] = int(v)
        elif k == "no_cache" and isinstance(v, str):
            result[k] = v.lower() in ("true", "1")
        else:
            result[k] = v
    return result


def map_api_call(action: str, params: dict) -> tuple[str, dict]:
    """返回 (milky_action, milky_params)."""
    params = _coerce_numbers(params)
    # 1. 需要参数转换的
    handler = _API_MAP.get(action)
    if handler:
        return handler(params)
    # 2. 仅名字不同的
    name = _NAME_MAP.get(action)
    if name:
        return name, params
    # 3. 名字相同, 原样透传
    return action, params


# ============================================================
# 消息类
# ============================================================

def _send_msg(params: dict) -> tuple[str, dict]:
    msg = params.get("message", [])
    if isinstance(msg, str):
        msg = [{"type": "text", "data": {"text": msg}}]
    milky_msg = [cq_to_milky(s).to_dict() for s in msg]

    if params.get("message_type") == "private":
        return "send_private_message", {"user_id": params["user_id"], "message": milky_msg}
    return "send_group_message", {"group_id": params["group_id"], "message": milky_msg}


def _delete_msg(params: dict) -> tuple[str, dict]:
    scene, peer_id, seq = unpack_msg_id(int(params["message_id"]))
    if scene == "friend":
        return "recall_private_message", {"user_id": peer_id, "message_seq": seq}
    return "recall_group_message", {"group_id": peer_id, "message_seq": seq}


def _get_msg(params: dict) -> tuple[str, dict]:
    scene, peer_id, seq = unpack_msg_id(int(params["message_id"]))
    return "get_message", {"message_scene": scene, "peer_id": peer_id, "message_seq": seq}


def _get_forward_msg(params: dict) -> tuple[str, dict]:
    return "get_forwarded_messages", {"forward_id": params.get("id", "")}


# ============================================================
# 群组管理
# ============================================================

def _set_group_ban(params: dict) -> tuple[str, dict]:
    return "set_group_member_mute", {
        "group_id": params["group_id"],
        "user_id": params["user_id"],
        "duration": params.get("duration", 0),
    }


def _set_group_admin(params: dict) -> tuple[str, dict]:
    return "set_group_member_admin", {
        "group_id": params["group_id"],
        "user_id": params["user_id"],
        "is_set": bool(params.get("enable", True)),
    }


def _set_group_add_request(params: dict) -> tuple[str, dict]:
    flag = params.get("flag", "")
    sub = params.get("sub_type", "add")
    if params.get("approve", True):
        return "accept_group_request", {
            "notification_seq": int(flag), "notification_type": sub,
            "group_id": params.get("group_id", 0), "is_filtered": False,
        }
    return "reject_group_request", {
        "notification_seq": int(flag), "notification_type": sub,
        "group_id": params.get("group_id", 0), "is_filtered": False,
        "reason": params.get("reason", ""),
    }


def _set_group_invitation(params: dict) -> tuple[str, dict]:
    if params.get("approve", True):
        return "accept_group_invitation", {
            "group_id": params["group_id"],
            "invitation_seq": int(params["flag"]),
        }
    return "reject_group_invitation", {
        "group_id": params["group_id"],
        "invitation_seq": int(params["flag"]),
    }


# ============================================================
# 好友
# ============================================================

def _set_friend_add_request(params: dict) -> tuple[str, dict]:
    flag = params.get("flag", "")
    if params.get("approve", True):
        return "accept_friend_request", {"initiator_uid": flag, "is_filtered": False}
    return "reject_friend_request", {
        "initiator_uid": flag, "is_filtered": False,
        "reason": params.get("remark", ""),
    }


# ============================================================
# 文件上传 (OneBot file/name → Milky file_uri/file_name)
# ============================================================

def _upload_group_file(params: dict) -> tuple[str, dict]:
    return "upload_group_file", {
        "group_id": params.get("group_id", 0),
        "file_uri": params.get("file", ""),
        "file_name": params.get("name", ""),
        "parent_folder_id": params.get("folder", "/"),
    }


def _upload_private_file(params: dict) -> tuple[str, dict]:
    return "upload_private_file", {
        "user_id": params.get("user_id", 0),
        "file_uri": params.get("file", ""),
        "file_name": params.get("name", ""),
    }


# ============================================================
# 参数字段转义 (OneBot 字段名 → Milky 字段名)
# ============================================================

def _set_group_whole_mute(params: dict) -> tuple[str, dict]:
    return "set_group_whole_mute", {
        "group_id": params.get("group_id", 0),
        "is_mute": bool(params.get("enable", True)),
    }


def _set_group_name(params: dict) -> tuple[str, dict]:
    return "set_group_name", {
        "group_id": params.get("group_id", 0),
        "new_group_name": params.get("group_name", ""),
    }


def _send_like(params: dict) -> tuple[str, dict]:
    return "send_profile_like", {
        "user_id": params.get("user_id", 0),
        "count": int(params.get("times", 1)),
    }


def _get_group_files(params: dict) -> tuple[str, dict]:
    return "get_group_files", {
        "group_id": params.get("group_id", 0),
        "parent_folder_id": params.get("folder_id", "/"),
    }


def _set_group_portrait(params: dict) -> tuple[str, dict]:
    return "set_group_avatar", {
        "group_id": params.get("group_id", 0),
        "image_uri": params.get("file", ""),
    }


def _set_qq_avatar(params: dict) -> tuple[str, dict]:
    return "set_avatar", {
        "uri": params.get("file", ""),
    }


def _create_group_folder(params: dict) -> tuple[str, dict]:
    return "create_group_folder", {
        "group_id": params.get("group_id", 0),
        "folder_name": params.get("name", ""),
    }


def _send_group_notice(params: dict) -> tuple[str, dict]:
    return "send_group_announcement", {
        "group_id": params.get("group_id", 0),
        "content": params.get("content", ""),
        "image_uri": params.get("image", ""),
    }


def _del_group_notice(params: dict) -> tuple[str, dict]:
    return "delete_group_announcement", {
        "group_id": params.get("group_id", 0),
        "announcement_id": params.get("notice_id", ""),
    }


def _move_group_file(params: dict) -> tuple[str, dict]:
    return "move_group_file", {
        "group_id": params.get("group_id", 0),
        "file_id": params.get("file_id", ""),
        "parent_folder_id": params.get("parent_directory", ""),
        "target_folder_id": params.get("target_directory", ""),
    }


def _get_group_essence_msgs(params: dict) -> tuple[str, dict]:
    return "get_group_essence_messages", {
        "group_id": params.get("group_id", 0),
        "page_index": params.get("page_index", 0),
        "page_size": params.get("page_size", 20),
    }


# ============================================================
# 扩展 API: 需要 message_id 解码
# ============================================================

def _set_group_reaction(params: dict) -> tuple[str, dict]:
    _, group_id, seq = unpack_msg_id(int(params["message_id"]))
    return "send_group_message_reaction", {
        "group_id": group_id or params.get("group_id", 0),
        "message_seq": seq,
        "reaction": str(params.get("code", "")),
        "reaction_type": "face",
        "is_add": bool(params.get("is_add", True)),
    }


def _set_essence_msg(params: dict) -> tuple[str, dict]:
    _, group_id, seq = unpack_msg_id(int(params["message_id"]))
    return "set_group_essence_message", {
        "group_id": group_id, "message_seq": seq, "is_set": True,
    }


def _delete_essence_msg(params: dict) -> tuple[str, dict]:
    _, group_id, seq = unpack_msg_id(int(params["message_id"]))
    return "set_group_essence_message", {
        "group_id": group_id, "message_seq": seq, "is_set": False,
    }


def _get_group_msg_history(params: dict) -> tuple[str, dict]:
    group_id = int(params.get("group_id", 0))
    # 优先取 message_id (桥编码), 其次 message_seq (原始序号)
    if params.get("message_id"):
        _, gid, seq = unpack_msg_id(int(params["message_id"]))
        group_id = gid or group_id
    else:
        seq = params.get("message_seq", 0)
    result = {"message_scene": "group", "peer_id": group_id,
              "limit": params.get("count", 20),
              "_reverse": params.get("reverseOrder", False)}
    if seq:
        result["start_message_seq"] = seq
    return "get_history_messages", result


def _get_friend_msg_history(params: dict) -> tuple[str, dict]:
    user_id = int(params.get("user_id", 0))
    if params.get("message_id"):
        _, uid, seq = unpack_msg_id(int(params["message_id"]))
        user_id = uid or user_id
    else:
        seq = params.get("message_seq", 0)
    result = {"message_scene": "friend", "peer_id": user_id,
              "limit": params.get("count", 20)}
    if seq:
        result["start_message_seq"] = seq
    return "get_history_messages", result


def _mark_msg_as_read(params: dict) -> tuple[str, dict]:
    scene, peer_id, seq = unpack_msg_id(int(params["message_id"]))
    return "mark_message_as_read", {
        "message_scene": scene, "peer_id": peer_id, "message_seq": seq,
    }


def _set_msg_emoji_like(params: dict) -> tuple[str, dict]:
    _, group_id, seq = unpack_msg_id(int(params["message_id"]))
    return "send_group_message_reaction", {
        "group_id": group_id or params.get("group_id", 0),
        "message_seq": seq,
        "reaction": str(params.get("emoji_id", "")),
        "reaction_type": "face",
        "is_add": bool(params.get("set", True)),
    }


# ============================================================
# 名字映射: Onebot API → Milky API (参数不变, 仅名字不同)
# ============================================================

_NAME_MAP = {
    "send_group_msg": "send_group_message",
    "send_private_msg": "send_private_message",
    "set_group_kick": "kick_group_member",
    "set_group_card": "set_group_member_card",
    "set_group_leave": "quit_group",
    "set_group_special_title": "set_group_member_special_title",
    "get_login_info": "get_login_info",
    "get_stranger_info": "get_user_profile",
    "get_friend_list": "get_friend_list",
    "get_group_info": "get_group_info",
    "get_group_list": "get_group_list",
    "get_group_member_info": "get_group_member_info",
    "get_group_member_list": "get_group_member_list",
    "get_cookies": "get_cookies",
    "get_csrf_token": "get_csrf_token",
    "get_group_honor_info": "get_group_honor_info",
    "get_forward_msg": "get_forwarded_messages",
    "send_group_nudge": "send_group_nudge",
    "get_group_notifications": "get_group_notifications",
    "delete_group_file": "delete_group_file",
    "get_group_file_url": "get_group_file_download_url",
    "get_resource_temp_url": "get_resource_temp_url",
    "get_impl_info": "get_impl_info",
    "get_version_info": "get_impl_info",
    # Lagrange 扩展 API → Milky
    "friend_poke": "send_friend_nudge",
    "group_poke": "send_group_nudge",
    "delete_group_file_folder": "delete_group_folder",
    "rename_group_file_folder": "rename_group_folder",
    "_get_group_notice": "get_group_announcements",
    "get_private_file_url": "get_private_file_download_url",
    "fetch_custom_face": "get_custom_face_url_list",
    "delete_friend": "delete_friend",
}

def _send_group_forward_msg(params: dict) -> tuple[str, dict]:
    """合并转发 → send_group_message + forward 段."""
    nodes = params.get("messages", [])
    fwd_messages = [_convert_node(n) for n in nodes]
    forward_seg = {"type": "forward", "data": {
        "messages": fwd_messages, "title": None,
        "preview": None, "summary": None, "prompt": None,
    }}
    return "send_group_message", {
        "group_id": params["group_id"],
        "message": [forward_seg],
    }


def _send_private_forward_msg(params: dict) -> tuple[str, dict]:
    nodes = params.get("messages", [])
    fwd_messages = [_convert_node(n) for n in nodes]
    forward_seg = {"type": "forward", "data": {
        "messages": fwd_messages, "title": None,
        "preview": None, "summary": None, "prompt": None,
    }}
    return "send_private_message", {
        "user_id": params["user_id"],
        "message": [forward_seg],
    }


def _convert_node(node: dict) -> dict:
    """Onebot node → Milky OutgoingForwardedMessage."""
    data = node.get("data", {})
    inner = data.get("content", [])
    return {
        "user_id": int(data.get("user_id", 0)),
        "sender_name": data.get("nickname", ""),
        "segments": [cq_to_milky(s).to_dict() for s in inner],
    }


# ============================================================
# 响应包装
# ============================================================

def wrap_response(milky_action: str, data: dict, params: dict) -> dict:
    """将 Milky API 响应包装为 Onebot v11 格式.

    原则: Milky 字段全部透传, 只翻译必须翻译的关键字段名.
    """
    match milky_action:

        # === 发送消息 ===
        case "send_group_message":
            seq = data.get("message_seq", 0)
            result = dict(data)
            result["message_id"] = pack_msg_id("group", params["group_id"], seq)
            return result
        case "send_private_message":
            seq = data.get("message_seq", 0)
            result = dict(data)
            result["message_id"] = pack_msg_id("friend", params["user_id"], seq)
            return result

        # === 获取消息 ===
        case "get_message":
            msg = data.get("message", dict(data))
            return _wrap_message(msg)

        # === 登录信息 ===
        case "get_login_info":
            result = dict(data)
            if "uin" in result:
                result["user_id"] = result.pop("uin")
            return result

        case "get_impl_info":
            result = dict(data)
            # 翻译为标准 Onebot 字段名, 同时保留原始 Milky 字段
            result["app_name"] = data.get("impl_name", "")
            result["app_version"] = data.get("impl_version", "")
            result["protocol_version"] = data.get("milky_version", "")
            result["nt_protocol"] = data.get("qq_protocol_type", "")
            return result

        # === 用户信息 ===
        case "get_user_profile":
            result = dict(data)
            result["user_id"] = params.get("user_id", data.get("user_id", 0))
            # OneBot 用 q_id/sign, Milky 用 qid/bio; 原始字段一并保留
            if "qid" in result:
                result["q_id"] = result["qid"]
            if "bio" in result:
                result["sign"] = result["bio"]
            return result

        # === 好友列表 ===
        case "get_friend_list":
            friends = data.get("friends", data if isinstance(data, list) else [])
            out = []
            for f in friends:
                f = dict(f)
                # OneBot 用 q_id, Milky 用 qid; group 为 OneBot 的好友分组别名, 保留 category
                if "qid" in f:
                    f["q_id"] = f["qid"]
                if "category" in f:
                    f["group"] = f["category"]
                out.append(f)
            return out

        # === 群信息 ===
        case "get_group_info":
            g = data.get("group", data)
            return dict(g)  # 全部字段透传

        # === 群列表 ===
        case "get_group_list":
            groups = data.get("groups", data if isinstance(data, list) else [])
            return [dict(g) for g in groups]

        # === 群成员信息 ===
        case "get_group_member_info":
            m = data.get("member", data)
            result = dict(m)
            result["group_id"] = params.get("group_id", m.get("group_id", 0))
            return result

        # === 群成员列表 ===
        case "get_group_member_list":
            members = data.get("members", data if isinstance(data, list) else [])
            return [dict(m) for m in members]

        # === 历史消息 ===
        case "get_history_messages":
            msgs = data.get("messages", [])
            result = [_wrap_message(msg) for msg in msgs]
            if params.get("_reverse"):
                result.reverse()
            return {"messages": result}

        case "get_forwarded_messages":
            msgs = data.get("messages", [])
            # OneBot get_forward_msg: data.message = [node{type,data{user_id,nickname,content[段列表]}}]
            nodes = []
            for m in msgs:
                content = [_milky_seg_to_cq_dict(s, "", 0) for s in m.get("segments", [])]
                nodes.append({
                    "type": "node",
                    "data": {
                        "user_id": 0,  # Milky 转发消息无发送者 QQ 号，仅 sender_name
                        "nickname": m.get("sender_name", ""),
                        "content": content,
                    },
                })
            # 同时提供 messages = 普通消息列表
            legacy = [_wrap_message(m) for m in msgs]
            return {"message": nodes, "messages": legacy}

        # === 文件下载链接: Milky 用 download_url, OneBot 用 url ===
        case "get_group_file_download_url" | "get_private_file_download_url":
            result = dict(data)
            if "download_url" in result:
                result["url"] = result.pop("download_url")
            return result

        # === CSRF: Milky 用 csrf_token, OneBot 用 token ===
        case "get_csrf_token":
            result = dict(data)
            if "csrf_token" in result:
                result["token"] = result["csrf_token"]
            return result

        # === 精华消息: Milky {messages,is_end} → OneBot 裸数组; 字段换名 ===
        case "get_group_essence_messages":
            msgs = data.get("messages", [])
            group_id = params.get("group_id", 0)
            out = []
            for m in msgs:
                m = dict(m)
                gid = group_id or m.get("group_id", 0)
                m["sender_nick"] = m.get("sender_name", "")
                m["sender_time"] = m.get("message_time", 0)
                m["operator_nick"] = m.get("operator_name", "")
                m["operator_time"] = m.get("operation_time", 0)
                m["message_id"] = pack_msg_id("group", gid, m.get("message_seq", 0))
                m["content"] = [_milky_seg_to_cq_dict(s, "group", gid) for s in m.get("segments", [])]
                out.append(m)
            return out

        # === 群公告: Milky {announcements} → OneBot 裸数组; 字段换名+message 对象化 ===
        case "get_group_announcements":
            anns = data.get("announcements", data if isinstance(data, list) else [])
            out = []
            for a in anns:
                a = dict(a)
                a["notice_id"] = a.get("announcement_id", "")
                a["sender_id"] = a.get("user_id", 0)
                a["publish_time"] = a.get("time", 0)
                img_url = a.get("image_url", "")
                a["message"] = {
                    "text": a.get("content", ""),
                    "images": [{"id": img_url}] if img_url else [],
                }
                out.append(a)
            return out

        # === 自定义表情: Milky {urls} → OneBot 裸数组 ===
        case "get_custom_face_url_list":
            urls = data.get("urls", data if isinstance(data, list) else [])
            return urls

        # === 群文件: 字段换名, 原始 Milky 字段一并透传 ===
        case "get_group_files":
            result = dict(data)
            new_files = []
            for f in data.get("files", []):
                f = dict(f)
                f["upload_time"] = f.get("uploaded_time", 0)
                f["dead_time"] = f.get("expire_time", 0)
                f["uploader"] = f.get("uploader_id", "")
                f["uploader_name"] = ""
                f["busid"] = ""
                new_files.append(f)
            new_folders = []
            for fo in data.get("folders", []):
                fo = dict(fo)
                fo["create_time"] = fo.get("created_time", 0)
                fo["creator"] = fo.get("creator_id", "")
                fo["create_name"] = ""
                fo["total_file_count"] = fo.get("file_count", 0)
                new_folders.append(fo)
            result["files"] = new_files
            result["folders"] = new_folders
            return result

        # === 默认: 原样透传 ===
        case _:
            return data


def _wrap_message(msg: dict) -> dict:
    """将单条 Milky 消息包装为 Onebot 格式. 字段全部透传, 只做必要翻译."""
    result = dict(msg)
    scene = msg.get("message_scene", "friend")
    peer = msg.get("peer_id", 0)
    seq = msg.get("message_seq", 0)

    # 段转换: segments → message (CQ 格式)
    result["message"] = [
        _milky_seg_to_cq_dict(s, scene, peer)
        for s in msg.get("segments", [])
    ]

    # 关键 ID 翻译
    result["message_id"] = pack_msg_id(scene, peer, seq)
    result["real_id"] = seq
    result["message_type"] = "group" if scene == "group" else "private"

    # sender: 透传整个 friend 或 group_member 对象
    sender = {}
    friend = msg.get("friend")
    group_member = msg.get("group_member")
    if group_member:
        sender = dict(group_member)
    elif friend:
        sender = dict(friend)
    sender.setdefault("user_id", msg.get("sender_id", 0))
    result["sender"] = sender

    return result


def _milky_seg_to_cq_dict(seg: dict, scene: str = "", peer_id: int = 0) -> dict:
    """Milky segment dict → Onebot CQ segment dict.

    统一委托 translator.milky_to_cq, 避免与事件推送路径各自维护一份转换逻辑而漂移.
    """
    from models import MilkySegment
    ms = MilkySegment(type=seg.get("type", ""), data=seg.get("data", {}))
    return milky_to_cq(ms, scene, peer_id).to_dict()


# ============================================================
# 映射表
# ============================================================

_API_MAP = {
    "send_msg": _send_msg,
    "send_group_msg": _send_msg,
    "send_private_msg": _send_msg,
    "delete_msg": _delete_msg,
    "get_msg": _get_msg,
    "get_forward_msg": _get_forward_msg,
    "set_group_ban": _set_group_ban,
    "set_group_admin": _set_group_admin,
    "set_group_add_request": _set_group_add_request,
    "set_group_invitation": _set_group_invitation,
    "set_friend_add_request": _set_friend_add_request,
    "set_group_reaction": _set_group_reaction,
    "set_essence_msg": _set_essence_msg,
    "delete_essence_msg": _delete_essence_msg,
    "get_group_msg_history": _get_group_msg_history,
    "get_friend_msg_history": _get_friend_msg_history,
    "mark_msg_as_read": _mark_msg_as_read,
    "set_msg_emoji_like": _set_msg_emoji_like,
    "send_group_forward_msg": _send_group_forward_msg,
    "send_private_forward_msg": _send_private_forward_msg,
    "upload_group_file": _upload_group_file,
    "upload_private_file": _upload_private_file,
    "set_group_whole_ban": _set_group_whole_mute,
    "set_group_name": _set_group_name,
    "send_like": _send_like,
    "get_group_files": _get_group_files,
    "get_group_root_files": _get_group_files,
    "get_group_files_by_folder": _get_group_files,
    "set_group_portrait": _set_group_portrait,
    "set_qq_avatar": _set_qq_avatar,
    "create_group_file_folder": _create_group_folder,
    "_send_group_notice": _send_group_notice,
    "_del_group_notice": _del_group_notice,
    "move_group_file": _move_group_file,
    "get_essence_msg_list": _get_group_essence_msgs,
    "send_group_reaction": _set_group_reaction,
    "set_group_essence_message": _set_essence_msg,
}
