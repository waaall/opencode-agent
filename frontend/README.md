# Agents Frontend (Sub-App)

Agents 前端是统一 Portal 体系下的子应用，单套代码同时支持：

- `Standalone`：本地独立开发（根路径 `/`）
- `Portal`：被主 Portal 通过 iframe 嵌入（子路径 `/apps/agents/`）

## Quick Start

```bash
cd frontend
npm install
npm run dev
```

默认开发地址：`http://localhost:3000`

## Runtime Config

所有配置通过 `VITE_` 环境变量注入，核心变量如下：

| 变量 | 说明 | 开发默认值 | Portal 生产默认值 |
|---|---|---|---|
| `VITE_BASE_PATH` | Vite 资源前缀 | `/` | `/apps/agents/` |
| `VITE_ROUTER_BASENAME` | React Router basename | `/` | `/apps/agents` |
| `VITE_EMBEDDED` | 是否运行在 Portal 嵌入模式 | `false` | `true` |
| `VITE_STORAGE_NS` | localStorage/sessionStorage 命名空间 | `agents` | `agents` |
| `VITE_COOKIE_PATH` | Cookie Path 建议值 | `/` | `/apps/agents/` |
| `VITE_API_BASE_URL` | API 基地址（不含 endpoint） | 空（走同源） | `/apps/agents` |
| `VITE_API_TIMEOUT` | 请求超时（ms） | `15000` | `15000` |

说明：旧变量 `VITE_API_BASE`、`VITE_API_TIMEOUT_MS` 已移除，不再兼容。

## API 组装规则

前端强制使用统一组装：

- endpoint 固定为绝对路径片段（例如 `/api/v1/jobs`）
- 最终 URL 通过 `joinUrl(VITE_API_BASE_URL, endpoint)` 生成

示例：

- `VITE_API_BASE_URL=` + `/api/v1/jobs` -> `/api/v1/jobs`
- `VITE_API_BASE_URL=/apps/agents` + `/api/v1/jobs` -> `/apps/agents/api/v1/jobs`
- `VITE_API_BASE_URL=https://orchestrator.example.com` + `/api/v1/jobs` -> `https://orchestrator.example.com/api/v1/jobs`

## Request Header 规范

API Client 会统一附加以下请求头：

- `X-Request-Id`：每次请求自动生成（可外部覆盖）
- `X-Client-Platform`：自动识别为 `web` 或 `desktop`
- `Authorization: Bearer <token>`：若本地存储存在 token

默认 token 读取顺序：

1. `${VITE_STORAGE_NS}:auth:token`（`localStorage`）
2. `${VITE_STORAGE_NS}:auth:token`（`sessionStorage`）
3. `auth_token`（`localStorage/sessionStorage`）

## Health Check

子应用健康检查文件：

- `public/health.json`

Portal 部署后应可访问：

- `/apps/agents/health.json`

## Dev Proxy

Vite 已内置代理，避免本地开发 CORS：

- `/api/* -> http://localhost:8000`
- `/apps/agents/api/* -> http://localhost:8000/api/*`（Portal 子路径联调）

## Desktop (Tauri) 构建说明

桌面构建时请覆盖：

- `VITE_API_BASE_URL=https://<your-backend-domain>`

并确保后端已放行桌面 Origin，且 Tauri `connect-src` 已加入该域名。
