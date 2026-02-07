# OpenCode Server（官网对齐版）

本文档仅保留可在 OpenAPI 契约中核对的信息；接口参数与返回类型以 `docs/api/opencode-api.json`（OpenAPI 3.1）为准。

## 1. 概述

OpenCode 支持 client/server 架构。`opencode serve` 会启动无界面 HTTP 服务，并暴露 OpenAPI 端点供客户端调用。

当你运行 `opencode` 时，会同时启动 TUI 和 Server；TUI 作为客户端与 Server 通信。`opencode serve` 可单独启动 Server；若 TUI 已在运行，再执行 `opencode serve` 会启动新的 Server 实例。

TUI 启动时会随机分配端口和主机名，也可通过 `--hostname` 和 `--port` 指定固定地址。`/tui` 相关端点可用于通过 Server 驱动 TUI（例如预填或提交 prompt），IDE 插件会使用这一能力。

## 2. 启动与认证

### 2.1 启动命令

```bash
opencode serve [--port <number>] [--hostname <string>] [--mdns] [--mdns-domain <string>] [--cors <origin>]
```

### 2.2 参数

| Flag | Description | Default |
|------|-------------|---------|
| `--port` | Port to listen on | `4096` |
| `--hostname` | Hostname to listen on | `127.0.0.1` |
| `--mdns` | Enable mDNS discovery | `false` |
| `--mdns-domain` | Custom domain name for mDNS service | `opencode.local` |
| `--cors` | Additional browser origins to allow | `[]` |

`--cors` 可多次传入：

```bash
opencode serve --cors http://localhost:5173 --cors https://app.example.com
```

### 2.3 Basic Auth

通过环境变量启用 HTTP Basic Auth：

```bash
OPENCODE_SERVER_PASSWORD=your-password opencode serve
```

- 用户名默认 `opencode`
- 可通过 `OPENCODE_SERVER_USERNAME` 覆盖
- 该鉴权同时作用于 `opencode serve` 与 `opencode web`

## 3. 最小调用流程

### 3.1 创建会话

```bash
curl -sS -X POST 'http://127.0.0.1:4096/session' \
  -H 'content-type: application/json' \
  -d '{"title":"headless-run"}'
```

### 3.2 发送消息并等待回复

```bash
curl -sS -X POST 'http://127.0.0.1:4096/session/{sessionID}/message' \
  -H 'content-type: application/json' \
  -d '{
    "agent": "build",
    "parts": [
      {"type":"text","text":"请分析当前仓库并给出改造方案"}
    ]
  }'
```

### 3.3 订阅事件流（SSE）

```bash
curl -N 'http://127.0.0.1:4096/event'
```

官方保证首个事件为 `server.connected`，后续为 bus 事件。

### 3.4 OpenAPI 契约文件

- 契约文件：`docs/api/opencode-api.json`

目录隔离参数（以契约文件为准）：

- OpenCode API 使用 query 参数 `directory` 指定工作目录。
- 示例：`GET /session/status?directory=/data/opencode-jobs/<job_id>`

## 4. API 参考

以下分组对齐官网 Server 页面。

### Global

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/global/health` | Get server health and version | `{ healthy: true, version: string }` |
| GET | `/global/event` | Get global events (SSE stream) | Event stream |

### Project

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/project` | 列出所有项目 | `Project[]` |
| GET | `/project/current` | 获取当前项目 | `Project` |

### Path & VCS

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/path` | 获取当前路径 | `Path` |
| GET | `/vcs` | 获取当前项目的 VCS 信息 | `VcsInfo` |

### Instance

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| POST | `/instance/dispose` | 销毁当前实例 | `boolean` |

### Config

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/config` | 获取配置信息 | `Config` |
| PATCH | `/config` | 更新配置 | `Config` |
| GET | `/config/providers` | 列出 provider 及默认模型 | `{ providers: Provider[], default: { [key: string]: string } }` |

### Provider

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/provider` | 列出所有 provider | `{ all: Provider[], default: {...}, connected: string[] }` |
| GET | `/provider/auth` | 获取 provider 认证方式 | `{ [providerID: string]: ProviderAuthMethod[] }` |
| POST | `/provider/{providerID}/oauth/authorize` | OAuth 授权 | `ProviderAuthAuthorization` |
| POST | `/provider/{providerID}/oauth/callback` | OAuth 回调 | `boolean` |

### Sessions

| Method | Path | Description | Notes |
|--------|------|-------------|-------|
| GET | `/session` | 列出所有会话 | 返回 `Session[]` |
| POST | `/session` | 创建新会话 | body: `{ parentID?, title? }`，返回 `Session` |
| GET | `/session/status` | 获取所有会话状态 | 返回 `{ [sessionID: string]: SessionStatus }` |
| GET | `/session/{sessionID}` | 获取会话详情 | 返回 `Session` |
| DELETE | `/session/{sessionID}` | 删除会话及其所有数据 | 返回 `boolean` |
| PATCH | `/session/{sessionID}` | 更新会话属性 | body: `{ title? }`，返回 `Session` |
| GET | `/session/{sessionID}/children` | 获取子会话 | 返回 `Session[]` |
| GET | `/session/{sessionID}/todo` | 获取会话的 todo 列表 | 返回 `Todo[]` |
| POST | `/session/{sessionID}/init` | 分析应用并创建 AGENTS.md | body: `{ messageID, providerID, modelID }`，返回 `boolean` |
| POST | `/session/{sessionID}/fork` | 在某条消息处分叉会话 | body: `{ messageID? }`，返回 `Session` |
| POST | `/session/{sessionID}/abort` | 中止正在运行的会话 | 返回 `boolean` |
| POST | `/session/{sessionID}/share` | 分享会话 | 返回 `Session` |
| DELETE | `/session/{sessionID}/share` | 取消分享 | 返回 `Session` |
| GET | `/session/{sessionID}/diff` | 获取会话的 diff | query: `messageID?`，返回 `FileDiff[]` |
| POST | `/session/{sessionID}/summarize` | 总结会话 | body: `{ providerID, modelID }`，返回 `boolean` |
| POST | `/session/{sessionID}/revert` | 回退消息 | body: `{ messageID, partID? }`，返回 `boolean` |
| POST | `/session/{sessionID}/unrevert` | 恢复所有已回退的消息 | 返回 `boolean` |
| POST | `/permission/{requestID}/reply` | 回复权限请求（推荐） | body: `{ reply, message? }`，返回 `boolean` |
| POST | `/session/{sessionID}/permissions/{permissionID}` | 回复权限请求（deprecated） | body: `{ response }`，返回 `boolean` |

### Messages

| Method | Path | Description | Notes |
|--------|------|-------------|-------|
| GET | `/session/{sessionID}/message` | 列出会话中的消息 | query: `limit?`，返回 `{ info: Message, parts: Part[] }[]` |
| POST | `/session/{sessionID}/message` | 发送消息并等待响应 | body: `{ messageID?, model?, agent?, noReply?, system?, tools?, parts }`，返回 `{ info: Message, parts: Part[] }` |
| GET | `/session/{sessionID}/message/{messageID}` | 获取消息详情 | 返回 `{ info: Message, parts: Part[] }` |
| GET | `/session/{sessionID}/message/{messageID}/part/{partID}` | 获取指定消息分片 | 返回 `Part` |
| POST | `/session/{sessionID}/prompt_async` | 异步发送消息（不等待） | body 同 `/session/{sessionID}/message`，返回 `204 No Content` |
| POST | `/session/{sessionID}/command` | 执行斜杠命令 | body: `{ messageID?, agent?, model?, command, arguments }`，返回 `{ info: Message, parts: Part[] }` |
| POST | `/session/{sessionID}/shell` | 执行 shell 命令 | body: `{ agent, model?, command }`，返回 `{ info: Message, parts: Part[] }` |

### Commands

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/command` | 列出所有命令 | `Command[]` |

### Files

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/find?pattern=<pat>` | 在文件中搜索文本 | 匹配对象数组（含 `path`, `lines`, `line_number`, `absolute_offset`, `submatches`） |
| GET | `/find/file?query=<q>` | 按名称查找文件和目录 | `string[]`（路径） |
| GET | `/find/symbol?query=<q>` | 查找工作区符号 | `Symbol[]` |
| GET | `/file?path=<path>` | 列出文件和目录 | `FileNode[]` |
| GET | `/file/content?path=<p>` | 读取文件内容 | `FileContent` |
| GET | `/file/status` | 获取已跟踪文件的状态 | `File[]` |

`/find/file` 查询参数：

| 参数 | 说明 |
|------|------|
| `query`（必填） | 搜索字符串（模糊匹配） |
| `type`（可选） | 限制结果类型：`"file"` 或 `"directory"` |
| `directory`（可选） | 覆盖项目根目录 |
| `limit`（可选） | 最大结果数（1–200） |
| `dirs`（可选） | 旧版标记（`"false"` 仅返回文件） |

### Agent

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/agent` | List all available agents | `Agent[]` |

### Logging

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| POST | `/log` | Write log entry | body: `{ service, level, message, extra? }`, returns `boolean` |

### TUI

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| POST | `/tui/append-prompt` | Append text to the prompt | `boolean` |
| POST | `/tui/open-help` | Open the help dialog | `boolean` |
| POST | `/tui/open-sessions` | Open the session selector | `boolean` |
| POST | `/tui/open-themes` | Open the theme selector | `boolean` |
| POST | `/tui/open-models` | Open the model selector | `boolean` |
| POST | `/tui/submit-prompt` | Submit the current prompt | `boolean` |
| POST | `/tui/clear-prompt` | Clear the prompt | `boolean` |
| POST | `/tui/execute-command` | Execute a command (`{ command }`) | `boolean` |
| POST | `/tui/show-toast` | Show toast (`{ title?, message, variant }`) | `boolean` |
| GET | `/tui/control/next` | Wait for the next control request | Control request object |
| POST | `/tui/control/response` | Respond to a control request (`{ body }`) | `boolean` |

### Auth

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| PUT | `/auth/{providerID}` | Set authentication credentials. Body must match provider schema | `boolean` |
| DELETE | `/auth/{providerID}` | Remove authentication credentials | `boolean` |

### Events

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/event` | Server-sent events stream. First event is `server.connected`, then bus events | Server-sent events stream |

## 5. 已知文档差异与落地规则

- 以 `docs/api/opencode-api.json` 为唯一契约来源（参数位置、必填项、返回结构都以此为准）。
- 官网 Server 文档与 SDK 文档在 `revert/unrevert` 返回类型上可能存在不一致时，按契约文件执行。
- 若 OpenAPI 导出在第三方工具中出现兼容问题，优先使用官方 SDK，或对 spec 做校验/清洗后再生成客户端。

## 6. 生产建议

- 必开 `OPENCODE_SERVER_PASSWORD`
- `hostname` 仅监听内网或配合反向代理
- 对 `/event` 做自动重连与心跳超时处理
- 固定 OpenCode 版本并回归关键链路（`session -> message -> event -> done`）
- 每次升级后重新抓取并校验 `docs/api/opencode-api.json`
