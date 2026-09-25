"""Milky WS 事件 → Onebot HTTP POST 事件."""
from dataclasses import asdict

from models import MilkyEvent, MilkyIncomingMessage, OnebotEvent
from translator import pack_msg_id, milky_to_cq


def strip_first_at_after_reply(ob: OnebotEvent) -> None:
    """删除回复段后的第一个 at 段 (原地修改).

    客户端在回复消息时经常自动附带 @对方 的段, 造成重复提及.
    只删除位于第一个 reply 段之后的第一个 at 段, 其余段保持原样.
    """
    message = ob.extra.get("message")
    if not isinstance(message, list):
        return
    try:
        first_reply = next(i for i, s in enumerate(message) if s.get("type") == "reply")
    except StopIteration:
        return
    for i in range(first_reply + 1, len(message)):
        if message[i].get("type") == "at":
            del message[i]
            return


def convert_event(event: MilkyEvent) -> OnebotEvent | None:
    handlers = {
        "message_receive": _message,
        "message_recall": _recall,
        "friend_request": _friend_request,
        "group_join_request": _group_join_request,
        "group_invited_join_request": _group_invited_join_request,
        "group_member_increase": _member_change,
        "group_member_decrease": _member_change,
        "group_message_reaction": _reaction,
        "group_nudge": _nudge,
        "friend_nudge": _friend_nudge,
        "group_admin_change": _group_admin_change,
        "group_mute": _group_mute,
        "group_whole_mute": _group_whole_mute,
        "group_file_upload": _group_file_upload,
        "friend_file_upload": _friend_file_upload,
        "peer_pin_change": _peer_pin_change,
        "bot_online": _bot_online,
        "bot_offline": _bot_offline,
        "group_invitation": _group_invitation,
        "group_name_change": _group_name_change,
        "group_essence_message_change": _essence,
        "essence": _essence,
        "offline_file": _offline_file,
    }
    handler = handlers.get(event.event_type)
    return handler(event) if handler else None


def _message(event: MilkyEvent) -> OnebotEvent:
    msg = MilkyIncomingMessage.from_dict(event.data)
    cqs = [milky_to_cq(s, msg.message_scene, msg.peer_id).to_dict() for s in msg.segments]
    raw = "".join(
        s.data.get("text", "") for s in msg.segments if s.type == "text"
    )
    message_id = pack_msg_id(msg.message_scene, msg.peer_id, msg.message_seq)

    # sender: 透传整个 group_member / friend 对象, user_id 确保存在
    if msg.group_member:
        sender = asdict(msg.group_member)
        sender.setdefault("user_id", msg.sender_id)
    elif msg.friend:
        sender = asdict(msg.friend)
        sender.setdefault("user_id", msg.sender_id)
    else:
        sender = {"user_id": msg.sender_id}

    if msg.message_scene == "group" and msg.group and msg.group_member:
        return OnebotEvent(
            time=event.time, self_id=event.self_id, post_type="message",
            extra={
                "message_type": "group", "sub_type": "normal",
                "message_id": message_id, "group_id": msg.group.group_id,
                "user_id": msg.sender_id, "anonymous": None,
                "message": cqs, "raw_message": raw, "font": 0,
                "sender": sender,
            },
        )
    elif msg.message_scene == "temp" and msg.group:
        return OnebotEvent(
            time=event.time, self_id=event.self_id, post_type="message",
            extra={
                "message_type": "private", "sub_type": "group",
                "message_id": message_id, "user_id": msg.sender_id,
                "message": cqs, "raw_message": raw, "font": 0,
                "group_id": msg.group.group_id,
                "sender": sender,
            },
        )
    else:
        return OnebotEvent(
            time=event.time, self_id=event.self_id, post_type="message",
            extra={
                "message_type": "private", "sub_type": "friend",
                "message_id": message_id, "user_id": msg.sender_id,
                "message": cqs, "raw_message": raw, "font": 0,
                "sender": sender,
            },
        )


def _recall(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    scene = d["message_scene"]
    message_id = pack_msg_id(scene, d["peer_id"], d["message_seq"])
    if scene == "group":
        return OnebotEvent(
            time=event.time, self_id=event.self_id, post_type="notice",
            extra={
                "notice_type": "group_recall", "group_id": d["peer_id"],
                "user_id": d["sender_id"], "operator_id": d["operator_id"],
                "message_id": message_id,
            },
        )
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "friend_recall", "user_id": d["sender_id"],
            "message_id": message_id,
        },
    )


def _friend_request(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="request",
        extra={
            "request_type": "friend",
            "user_id": d.get("initiator_id", 0),
            "comment": d.get("comment", ""),
            "flag": d.get("initiator_uid", ""),
        },
    )


def _group_join_request(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="request",
        extra={
            "request_type": "group", "sub_type": "add",
            "group_id": d.get("group_id", 0),
            "user_id": d.get("initiator_id", 0),
            "comment": d.get("comment", ""),
            "flag": str(d.get("notification_seq", "")),
        },
    )


def _group_invited_join_request(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="request",
        extra={
            "request_type": "group", "sub_type": "invite",
            "group_id": d.get("group_id", 0),
            "user_id": d.get("initiator_id", 0),
            "comment": "",
            "flag": str(d.get("notification_seq", "")),
        },
    )


def _member_change(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    is_inc = event.event_type == "group_member_increase"
    if is_inc:
        # Milky 字段: user_id, operator_id(nullable), invitor_id(nullable)
        # 有 invitor_id → invite, 否则 approve
        sub_type = "invite" if d.get("invitor_id") else "approve"
        operator_id = d.get("operator_id") or d.get("invitor_id") or 0
    else:
        # Milky 字段: user_id, operator_id(nullable)
        # 有 operator_id 且不等于 user_id → kick, 否则 leave
        uid = d.get("user_id", 0)
        op_id = d.get("operator_id") or 0
        sub_type = "kick" if op_id and op_id != uid else "leave"
        operator_id = op_id
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "group_increase" if is_inc else "group_decrease",
            "sub_type": sub_type,
            "group_id": d.get("group_id", 0),
            "user_id": d.get("user_id", 0),
            "operator_id": operator_id,
        },
    )


def _reaction(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    # Milky 字段: group_id, user_id, message_seq, face_id, reaction_type, is_add
    group_id = d.get("group_id", 0)
    msg_id = pack_msg_id("group", group_id, d.get("message_seq", 0))
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "reaction",
            "group_id": group_id, "message_id": msg_id,
            "operator_id": d.get("user_id", 0),
            "sub_type": "add" if d.get("is_add", False) else "remove",
            "code": str(d.get("face_id", "")),
            "count": 1,
        },
    )


def _nudge(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    # Milky 字段: group_id, sender_id, receiver_id
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "poke",
            "group_id": d.get("group_id", 0),
            "user_id": d.get("sender_id", 0),
            "target_id": d.get("receiver_id", 0),
        },
    )


def _bot_online(event: MilkyEvent) -> OnebotEvent:
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={"notice_type": "bot_online"},
    )


def _bot_offline(event: MilkyEvent) -> OnebotEvent:
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={"notice_type": "bot_offline"},
    )


def _group_invitation(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    # Milky 字段: group_id, invitation_seq, initiator_id, source_group_id
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="request",
        extra={
            "request_type": "group_invited",
            "group_id": d.get("group_id", 0),
            "user_id": d.get("initiator_id", 0),
            "flag": str(d.get("invitation_seq", "")),
        },
    )


def _group_name_change(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    # Milky 字段: group_id, new_group_name, operator_id
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "group_name_change",
            "group_id": d.get("group_id", 0),
            "name": d.get("new_group_name", ""),
        },
    )


def _essence(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    # Milky 字段: group_id, message_seq, operator_id(v1.1+), is_set
    msg_id = pack_msg_id("group", d.get("group_id", 0), d.get("message_seq", 0))
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "essence",
            "sub_type": "add" if d.get("is_set", True) else "delete",
            "group_id": d.get("group_id", 0),
            "operator_id": d.get("operator_id", 0),
            "message_id": msg_id,
        },
    )


def _friend_nudge(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    # Milky 字段: user_id, is_self_send, is_self_receive, display_action...
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "friend_poke",
            "user_id": d.get("user_id", 0),
            "target_id": event.self_id if d.get("is_self_receive") else d.get("user_id", 0),
        },
    )


def _group_admin_change(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    # Milky 字段: group_id, user_id, operator_id(v1.1+), is_set
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "group_admin",
            "sub_type": "set" if d.get("is_set", False) else "unset",
            "group_id": d.get("group_id", 0),
            "user_id": d.get("user_id", 0),
            "operator_id": d.get("operator_id", 0),
        },
    )


def _group_mute(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    # Milky 字段: group_id, user_id, operator_id, duration
    duration = d.get("duration", 0)
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "group_ban",
            "sub_type": "ban" if duration > 0 else "lift_ban",
            "group_id": d.get("group_id", 0),
            "user_id": d.get("user_id", 0),
            "operator_id": d.get("operator_id", 0),
            "duration": duration,
        },
    )


def _group_whole_mute(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    # Milky 字段: group_id, operator_id, is_mute
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "group_ban",
            "sub_type": "whole_ban" if d.get("is_mute", False) else "whole_lift_ban",
            "group_id": d.get("group_id", 0),
            "operator_id": d.get("operator_id", 0),
        },
    )


def _group_file_upload(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    # Milky 字段: group_id, user_id, file_id, file_name, file_size
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "group_upload",
            "group_id": d.get("group_id", 0),
            "user_id": d.get("user_id", 0),
            "file": {
                "id": d.get("file_id", ""),
                "name": d.get("file_name", ""),
                "size": d.get("file_size", 0),
            },
        },
    )


def _friend_file_upload(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    # Milky 字段: user_id, file_id, file_name, file_size, file_hash, is_self
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "offline_file",
            "user_id": d.get("user_id", 0),
            "file": {
                "id": d.get("file_id", ""),
                "name": d.get("file_name", ""),
                "size": d.get("file_size", 0),
            },
        },
    )


def _peer_pin_change(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    # Milky 字段 (v1.2): message_scene, peer_id, is_pinned
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "peer_pin_change",
            "message_scene": d.get("message_scene", ""),
            "peer_id": d.get("peer_id", 0),
            "is_pinned": d.get("is_pinned", False),
        },
    )


def _offline_file(event: MilkyEvent) -> OnebotEvent:
    d = event.data
    return OnebotEvent(
        time=event.time, self_id=event.self_id, post_type="notice",
        extra={
            "notice_type": "offline_file",
            "user_id": d.get("sender_id", 0),
            "file": {
                "id": d.get("file_id", ""),
                "name": d.get("file_name", ""),
                "size": d.get("file_size", 0),
                "url": d.get("file_url", ""),
            },
        },
    )
