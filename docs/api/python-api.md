# Python Backend API（FastAPI）

本文档只定义 Python 编排后端对前端暴露的 API 契约，用于和 OpenCode API 明确区分。

## 1. 边界

- 前端调用：`/api/v1/*`（本文件）
- Python 后端内部调用 OpenCode：`/global/*`、`/session/*`、`/event` 等（不对前端暴露）

OpenCode 契约参考：

- `/Users/zhengxu/Desktop/some_code/opencode-agent/docs/api/opencode-server.md`
- `/Users/zhengxu/Desktop/some_code/opencode-agent/docs/api/opencode-api.json`

## 2. 统一前缀

- Base Path：`/api/v1`

## 3. Job 状态

- `created`
- `queued`
- `running`
- `waiting_approval`
- `verifying`
- `packaging`
- `succeeded`
- `failed`
- `aborted`

## 4. 对外 API（前端 -> Python）

| Method | Path | 说明 |
|---|---|---|
| POST | `/api/v1/jobs` | 创建任务与工作区，保存 `requirement` 与上传文件 |
| POST | `/api/v1/jobs/{job_id}/start` | 启动异步执行（入队） |
| GET | `/api/v1/jobs/{job_id}` | 查询任务详情（状态、session、错误、产物摘要） |
| GET | `/api/v1/jobs/{job_id}/events` | SSE 事件流（任务状态变化） |
| POST | `/api/v1/jobs/{job_id}/abort` | 终止任务 |
| GET | `/api/v1/jobs/{job_id}/artifacts` | 查询产物清单 |
| GET | `/api/v1/jobs/{job_id}/download` | 下载打包结果 `result.zip` |
| GET | `/api/v1/jobs/{job_id}/artifacts/{artifact_id}/download` | 可选：下载单个产物 |
| GET | `/api/v1/skills` | 查询技能列表（支持 `task_type?`） |
| GET | `/api/v1/skills/{skill_code}` | 查询单个技能元数据与输出契约 |

## 5. 关键请求字段

### `POST /api/v1/jobs`

| 字段 | 必填 | 说明 |
|---|---|---|
| `requirement` | 是 | 用户需求文本 |
| `files[]` | 是 | 上传文件，至少 1 个 |
| `skill_code` | 否 | 手动指定技能 |
| `agent` | 否 | 默认 `build` |
| `model` | 否 | 指定模型 |
| `output_contract` | 否 | JSON 字符串，声明必需产物 |
| `idempotency_key` | 否 | 幂等键 |

## 6. 关键返回语义

- `POST /api/v1/jobs`：返回 `job_id`、`status=created`
- `POST /api/v1/jobs/{job_id}/start`：返回 `status=queued`
- `GET /api/v1/jobs/{job_id}/download`：返回统一打包产物（`bundle/result.zip`）

## 7. 前后端与 OpenCode 的职责分离

- 前端只调用 `/api/v1/*`，不直接调用 OpenCode。
- Python 后端负责把任务编排成 OpenCode 调用流程，并把 OpenCode 事件转换成业务状态。
- Python 后端调用 OpenCode 时统一附加 `directory=/data/opencode-jobs/{job_id}`，该参数不属于前端 API。
