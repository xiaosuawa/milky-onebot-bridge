# milky-onebot-bridge

Milky 协议与 OneBot v11 协议之间的双向桥接服务。

OneBot v11协议有许多的问题，社区推出了新一代的 Milky 协议，已经有部分实现端采用，但还有许多应用使用老的协议进行开发，通过本项目你可以让部分老应用也能在新协议的实现端上使用。

上游 [Milky](https://milky.ntqqrev.org)（QQ 机器人应用接口标准）提供 WebSocket 事件推送与 HTTP API；下游调用方按 OneBot v11 规范收发消息。本桥同时作为 **OneBot 实现端**（对外提供 HTTP API）与 **Milky 客户端**（接收 WS 事件、调用 Milky API），在两侧之间做协议翻译。

本项目主要用于作者自己的项目，存在许多的问题，欢迎贡献代码修复他们，也可以通过 Issue 反馈。但个人精力有限，可能无法及时处理这些请求。

## 快速开始

需要 Python 3.12+。
克隆或下载本项目源码，然后再目录中执行：

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

pip install -r requirements.txt
python main.py
```

首次运行时会自动从 `config.example.yaml` 生成 `config.yaml`，按需修改后重启即可。`config.yaml` 不入版本控制，可安全填写 access token。

## 配置

全部配置项位于 `bridge` 下：

```yaml
bridge:
  onebot:
    listen_host: "127.0.0.1"
    listen_port: 5600        # 对应调用方的 api.host:port
    access_token: ""
    event_push_url: "http://127.0.0.1:5601/"   # 桥主动 POST 事件的目标地址

  milky:
    ws_url: "ws://127.0.0.1:8090/event"
    http_url: "http://127.0.0.1:8090"
    access_token: ""

  skip_self_message: true    # 忽略机器人自己的消息，避免回环
  extensions:
    strip_at_after_reply: true  # 删除回复段后的第一个 @ 段
```

| 配置项 | 说明 |
|---|---|
| `onebot.listen_host` / `listen_port` | 桥作为 OneBot 实现端对外监听的地址 |
| `onebot.access_token` | 桥校验调用方请求、并在推送事件时携带的 Bearer token |
| `onebot.event_push_url` | 事件上报地址，调用方在此接收 OneBot 事件 |
| `milky.ws_url` | Milky 事件推送 WebSocket 地址 |
| `milky.http_url` | Milky HTTP API 根地址，请求路径为 `/api/{action}` |
| `milky.access_token` | 访问 Milky 所用的 Bearer token |
| `skip_self_message` | 丢弃发送者为机器人自身的消息，防止消息回环 |
| `extensions.strip_at_after_reply` | 客户端回复时通常会自动附带 `@对方`，该段与回复语义重复，开启后自动删除回复段后的第一个 at 段 |

## 注意事项

### message_id 超出常规整数范围

OneBot v11 规范中 `message_id` 为 32 位整数，而本桥需要用它承载 Milky 的 `(message_scene, peer_id, message_seq)` 三元组，编码后的位宽远超 32 位：

| 场景 | 编码后位宽 |
|---|---|
| 小号私聊 | 35 bit |
| 典型群聊 | 49 bit |
| 大群 + 较大 `message_seq` | 79 bit |

Python 的 `int` 是任意精度，Python 应用通常不会有问题（本桥即用 Python 编写）。但其他语言的接入方需要注意：

- Java / Go / C++ 等按固定宽度处理整数时，`int32` 必然溢出，`message_seq` 较大时 `int64` 也会溢出
- JavaScript 的 `Number` 安全整数上限为 2^53，超出会**静默丢失精度**。本桥通过 JSON 传递 `message_id`，接入方若为 JS / TS 应以 `BigInt` 或字符串处理

### 包含非标准字段

除 OneBot v11 标准外，本项目还实现了一批扩展字段，它们按 **Lagrange.Onebot V1** 的接口约定设计，包括但不限于：

- 扩展 API：`send_group_forward_msg`、`set_group_reaction`、`_send_group_notice`、`get_group_files` 系列、`get_private_file_url`、`fetch_custom_face`、`friend_poke` / `group_poke` 等
- 消息段：`mface`（商城表情）、`markdown`、`keyboard`、`poke` 等
- `notice_type`：`reaction`、`poke`、`friend_poke`、`bot_online`、`bot_offline`、`group_name_change`、`peer_pin_change` 等

按标准 OneBot v11 实现的接入方，需要按 Lagrange 的约定处理这些字段。

### 不处理 CQ 码

OneBot v11 的消息有两种表示：**数组格式**（`[{"type": "at", "data": {"qq": "123"}}]`）与 **CQ 码字符串格式**（`"[CQ:at,qq=123]"`）。本桥只支持数组格式，不实现 CQ 码的解析与生成：

- **发送消息**：`message` 传入字符串时按**纯文本**处理，其中的 `[CQ:xxx]` 不会被解析成消息段，会原样发出
- **接收消息**：`raw_message` 只拼接各文本段的 `text`，不含 CQ 码字符串——与 OneBot v11 规范中该字段为 CQ 码格式的定义不同
- **合并转发**：节点 `content` 必须是消息段数组，传入 CQ 码字符串会因按段迭代而出错

接入方请统一使用消息段数组收发。

## 支持的 API 与事件

API 映射位于 `api_mapping.py`，按三级策略解析：需要参数转换的走映射函数，仅名字不同的换名后透传，名字相同则原样透传。共覆盖 66 个 API，未收录的 action 会原样转发给 Milky。

事件映射位于 `event_mapping.py`，覆盖 23 种 Milky 事件；未识别的事件类型会被跳过，不会断开连接。

## 许可证

[Apache License 2.0](LICENSE)