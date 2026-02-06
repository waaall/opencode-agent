# OpenCode 无界面服务（Headless）使用说明

本文档说明如何把 OpenCode 当作无界面服务运行，并给出 API 的权威来源与最小调用流程。

## 1. 什么是无界面服务

OpenCode 支持 client/server 架构。你可以仅启动服务端（不打开 TUI），然后由 Python/Node/其他后端通过 HTTP API 调用。

- 启动命令入口：`opencode serve`
- 服务端实现：`packages/opencode/src/server/server.ts`
- 会话执行主路由：`packages/opencode/src/server/routes/session.ts`

## 2. 快速启动（无界面）

### 2.1 本地启动

```bash
opencode serve --hostname 127.0.0.1 --port 4096
```

启动成功后会输出：

```text
opencode server listening on http://127.0.0.1:4096
```

### 2.2 关键参数

- `--hostname`：监听地址（默认 `127.0.0.1`）
- `--port`：监听端口（传 `0` 时会优先尝试 `4096`，失败再随机端口）
- `--mdns` / `--mdns-domain`：局域网发现相关
- `--cors`：附加 CORS 白名单

参数定义见：`packages/opencode/src/cli/network.ts`。

### 2.3 鉴权（强烈建议开启）

服务支持 Basic Auth。若不设置密码，服务默认无保护。

```bash
export OPENCODE_SERVER_PASSWORD='change-me'
export OPENCODE_SERVER_USERNAME='opencode' # 可选，默认就是 opencode
opencode serve --hostname 127.0.0.1 --port 4096
```

请求时添加 `Authorization: Basic ...`。

### 2.4 工作目录绑定（非常重要）

服务每个请求都会绑定目录上下文，优先级：

1. query 参数 `directory`
2. header `x-opencode-directory`
3. 服务进程当前工作目录

建议服务调用方显式传 `x-opencode-directory`，避免跨项目串上下文。

## 3. 最小调用流程（适合 Python 后端编排）

### 3.1 创建会话

```bash
curl -sS -X POST 'http://127.0.0.1:4096/session' \
  -H 'content-type: application/json' \
  -H 'x-opencode-directory: /absolute/path/to/project' \
  -d '{"title":"headless-run"}'
```

### 3.2 发送 Prompt

```bash
curl -sS -X POST 'http://127.0.0.1:4096/session/<sessionID>/message' \
  -H 'content-type: application/json' \
  -H 'x-opencode-directory: /absolute/path/to/project' \
  -d '{
    "agent": "build",
    "parts": [
      {"type":"text","text":"请分析当前仓库并给出改造方案"}
    ]
  }'
```

### 3.3 订阅事件流（SSE）

```bash
curl -N 'http://127.0.0.1:4096/event?directory=/absolute/path/to/project'
```

你会看到例如：

- `server.connected`
- `message.part.updated`
- `session.status`（当状态变为 `idle`，通常可视为本轮完成）
- `permission.asked`
- `question.asked`

### 3.4 处理阻塞请求（permission/question）

当 Agent 需要人工确认：

```bash
# 列出待处理权限
curl -sS 'http://127.0.0.1:4096/permission?directory=/absolute/path/to/project'

# 回复权限请求
curl -sS -X POST 'http://127.0.0.1:4096/permission/<requestID>/reply' \
  -H 'content-type: application/json' \
  -d '{"reply":"once"}'

# 列出待处理问题
curl -sS 'http://127.0.0.1:4096/question?directory=/absolute/path/to/project'

# 回复问题请求
curl -sS -X POST 'http://127.0.0.1:4096/question/<requestID>/reply' \
  -H 'content-type: application/json' \
  -d '{"answers":[["你的选项文本"]]}'
```

## 4. Skill 与 Agent 的无界面使用方式

### 4.1 查看可用 Agent / Skill

```bash
curl -sS 'http://127.0.0.1:4096/agent?directory=/absolute/path/to/project'
curl -sS 'http://127.0.0.1:4096/skill?directory=/absolute/path/to/project'
```

### 4.2 Skill 发现目录

服务会自动扫描：

- `.opencode/skill/**/SKILL.md`
- `.opencode/skills/**/SKILL.md`
- `.claude/skills/**/SKILL.md`
- `.agents/skills/**/SKILL.md`
- `config.skills.paths` 配置的附加目录

实现见：`packages/opencode/src/skill/skill.ts`。

说明：Headless API 没有“直接执行某个 skill”的独立端点。Skill 由 Agent 在会话中通过工具链自动选择和调用。

## 5. 详细 API 文档（不重复维护）

本仓库已经有完整 OpenAPI。这里作为权威来源，不在本文重复字段级定义。

### 5.1 运行时文档（推荐）

服务启动后访问：

- `GET /doc`
- 例如：`http://127.0.0.1:4096/doc`

### 5.2 仓库静态规范

- `packages/sdk/openapi.json`

你可以直接用该文件生成 Python 客户端（如 `openapi-python-client` 或 `datamodel-code-generator`）。

### 5.3 Headless 常用 API 分组

- 会话：`/session`, `/session/status`, `/session/{sessionID}/message`, `/session/{sessionID}/prompt_async`, `/session/{sessionID}/abort`
- 事件：`/event`, `/global/event`
- 审批：`/permission`, `/permission/{requestID}/reply`, `/question`, `/question/{requestID}/reply`
- 能力探测：`/agent`, `/skill`, `/command`, `/provider`, `/mcp`
- 运行上下文：`/path`, `/project`, `/config`

完整列表以 OpenAPI 为准。

## 6. 生产建议

- 必开 `OPENCODE_SERVER_PASSWORD`
- `hostname` 仅监听内网或配合反向代理
- 每次请求显式传 `x-opencode-directory`
- 对 `/event` 使用重连与心跳超时处理
- 对 `permission/question` 设计超时策略（避免任务永久挂起）
- 固定 OpenCode 版本并回归关键流程（`session -> prompt -> event -> done`）

