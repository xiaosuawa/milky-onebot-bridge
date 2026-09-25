"""Milky 和 Onebot 数据结构."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


# ============================================================
# Milky WS 事件
# ============================================================

@dataclass
class MilkyEvent:
    event_type: str
    time: int
    self_id: int
    data: Any


# ============================================================
# Milky 消息段
# ============================================================

@dataclass
class MilkySegment:
    type: str
    data: dict[str, Any]

    @classmethod
    def from_dict(cls, d: dict) -> MilkySegment:
        return cls(type=d["type"], data=d.get("data", {}))


# ============================================================
# Milky 入站消息
# ============================================================

@dataclass
class MilkyIncomingMessage:
    message_scene: str
    peer_id: int
    message_seq: int
    sender_id: int
    time: int
    segments: list[MilkySegment]
    group: MilkyGroup | None = None
    group_member: MilkyGroupMember | None = None
    friend: MilkyFriend | None = None

    @classmethod
    def from_dict(cls, d: dict) -> MilkyIncomingMessage:
        group = MilkyGroup(**d["group"]) if d.get("group") else None
        member = MilkyGroupMember(**d["group_member"]) if d.get("group_member") else None
        friend = MilkyFriend(**d["friend"]) if d.get("friend") else None
        return cls(
            message_scene=d["message_scene"],
            peer_id=d["peer_id"],
            message_seq=d["message_seq"],
            sender_id=d["sender_id"],
            time=d["time"],
            segments=[MilkySegment.from_dict(s) for s in d.get("segments", [])],
            group=group,
            group_member=member,
            friend=friend,
        )


@dataclass
class MilkyGroup:
    group_id: int
    group_name: str
    member_count: int = 0
    max_member_count: int = 0
    remark: str = ""
    created_time: int = 0
    description: str = ""
    question: str = ""
    announcement: str = ""


@dataclass
class MilkyGroupMember:
    user_id: int
    nickname: str
    sex: str = "unknown"
    group_id: int = 0
    card: str = ""
    title: str = ""
    level: int = 0
    role: str = "member"
    join_time: int = 0
    last_sent_time: int = 0
    shut_up_end_time: int = 0


@dataclass
class MilkyFriend:
    user_id: int
    nickname: str
    sex: str = "unknown"
    remark: str = ""
    level: int = 0
    age: int = 0
    qid: str = ""
    country: str = ""
    city: str = ""


# ============================================================
# Onebot CQ 段
# ============================================================

@dataclass
class CQSegment:
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"type": self.type, "data": self.data}


# ============================================================
# Onebot 事件
# ============================================================

@dataclass
class OnebotEvent:
    time: int
    self_id: int
    post_type: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "time": self.time,
            "self_id": self.self_id,
            "post_type": self.post_type,
            **self.extra,
        }


# ============================================================
# Onebot API 请求 (调用方 → 桥)
# ============================================================

@dataclass
class OnebotAPIRequest:
    action: str
    params: dict[str, Any]
    echo: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> OnebotAPIRequest:
        return cls(action=d["action"], params=d.get("params", {}), echo=d.get("echo"))


# ============================================================
# Milky 出站段 (发送消息用)
# ============================================================

@dataclass
class MilkyOutgoingSegment:
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"type": self.type, "data": self.data}
