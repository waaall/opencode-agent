# OpenCode Orchestrator

FastAPI + Celery 后端服务，供 Agents 子应用调用。

## 文档导航

- 详细后端架构设计（整体设计、关键流程、状态机、可靠性策略）：[`../../docs/design/backend-design.md`](../../docs/design/backend-design.md)
- 本 README 聚焦本地运行、接口入口与联调约定。

## Run (Local)

```bash
cd services/orchestrator
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

Worker:

```bash
cd services/orchestrator
source .venv/bin/activate
celery -A app.worker.celery_app.celery_app worker -Q default --concurrency=12
```

## API 与健康检查

- API 前缀：`/api/v1`
- 健康检查：`GET /health`（兼容保留 `GET /healthz`）

核心接口（节选）：

- `POST /api/v1/jobs`
- `POST /api/v1/jobs/{job_id}/start`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/events`
- `POST /api/v1/jobs/{job_id}/abort`
- `GET /api/v1/jobs/{job_id}/artifacts`
- `GET /api/v1/skills`

## 前端协同约定（Agents 子应用）

Agents 前端使用 `VITE_API_BASE_URL + /api/v1/*` 组装 URL，例如：

- 同域网关：`/apps/agents/api/v1/*`
- 直连后端：`https://<backend-domain>/api/v1/*`

后端接受并透传以下请求头：

- `X-Request-Id`（若缺失则服务端自动生成并回写到响应头）
- `X-Client-Platform`（`web`/`desktop`）
- `Authorization: Bearer <token>`（按你的鉴权中间件策略使用）

## CORS 配置（App/Tauri 场景）

默认不启用跨域。需要桌面端直连时，请通过环境变量显式配置白名单：

```bash
export CORS_ALLOWED_ORIGINS="http://localhost:3000,tauri://localhost"
export CORS_ALLOWED_METHODS="GET,POST,PUT,PATCH,DELETE,OPTIONS"
export CORS_ALLOWED_HEADERS="Authorization,Content-Type,X-Request-Id,X-Client-Platform"
export CORS_ALLOW_CREDENTIALS=false
```

说明：

- `CORS_ALLOWED_ORIGINS` 为空时不添加 CORS 中间件（推荐 Web 同域网关模式）
- 如需 Cookie 鉴权，`CORS_ALLOW_CREDENTIALS=true` 且 `CORS_ALLOWED_ORIGINS` 不能用 `*`

## Core Env

```bash
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/orchestrator
export REDIS_URL=redis://localhost:6379/0
export DATA_ROOT=./data/opencode-jobs
export OPENCODE_BASE_URL=http://localhost:4096
export OPENCODE_SERVER_USERNAME=opencode
export OPENCODE_SERVER_PASSWORD=your-password
```
