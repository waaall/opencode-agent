# OpenCode Orchestrator 后端整体设计（当前实现版）

## 1. 文档定位

本文档定义当前 `services/orchestrator` 的后端设计，以已实现代码为准。

- 技术栈：FastAPI + Celery + Redis + SQLAlchemy
- 执行内核：OpenCode Server（通过 HTTP API 调用）
- 设计原则：统一任务流水线、Skill 模块化、工作区隔离、严格状态机
- 兼容策略：不做向后兼容，直接采用当前最优设计

---

## 2. 总体架构

### 2.1 组件分层

- API 层：`services/orchestrator/app/api/v1/*`
  - 提供 `/api/v1/jobs*`、`/api/v1/skills*` 接口
- 应用层：`services/orchestrator/app/application/*`
  - `OrchestratorService` 负责创建/启动/终止/查询任务
  - `JobExecutor` 负责单任务执行状态推进
- 领域层：`services/orchestrator/app/domain/*`
  - 状态机枚举、JobContext、Skill 基类和具体 Skill
- 基础设施层：`services/orchestrator/app/infra/*`
  - DB Repository、OpenCode Client、OpenCode EventBridge、Workspace/Artifact、Permission Policy
- 异步执行层：`services/orchestrator/app/worker/*`
  - Celery task 调度和重试

### 2.2 关键职责边界

- FastAPI：上传/任务编排/状态与产物接口
- Celery Worker：异步执行与状态流转
- OpenCode：实际 AI 执行与工具调用
- 本地存储：每个 Job 独立工作目录

### 2.3 生命周期与容器管理

- FastAPI 采用 `lifespan` 初始化与回收（不再使用 `@app.on_event("startup")`）
  - 启动阶段执行 `init_db()`
  - 退出阶段执行 `shutdown_container_resources()`
- 容器依赖以单例缓存组织（`@lru_cache(maxsize=1)`）
  - `OpenCodeClient`、`OpenCodeEventBridge`、Repository、Service、Executor 等在进程内复用
- 长连接资源显式关闭
  - API 进程在 `lifespan shutdown` 时关闭 HTTP 客户端与 SSE 客户端
  - Celery 进程在 `worker_process_shutdown` 时执行同一套资源回收

---

## 3. 工作区模型

每个 Job 对应独立目录（`DATA_ROOT/{job_id}`）：

```text
{job_id}/
  job/
    request.md
    execution-plan.json
  inputs/
  outputs/
  logs/
    opencode-last-message.md
  bundle/
    result.zip
    manifest.json
```

约束：

- 上传文件写入 `inputs/`，文件名做安全规范化
- 结果验收目录为 `outputs/`
- 打包产物由后端生成到 `bundle/result.zip`

---

## 4. API 契约（对前端）

统一前缀：`/api/v1`

### 4.1 Job API

1. `POST /jobs`
- `multipart/form-data`
- 字段：
  - `requirement`（必填）
  - `files[]`（必填，至少一个）
  - `skill_code`（可选）
  - `agent`（可选）
  - `model_provider_id`（可选，需与 `model_id` 成对）
  - `model_id`（可选，需与 `model_provider_id` 成对）
  - `output_contract`（可选 JSON 字符串）
  - `idempotency_key`（可选）
- 返回：`job_id`、`status`、`selected_skill`

2. `POST /jobs/{job_id}/start`
- 将任务入队执行

3. `GET /jobs/{job_id}`
- 返回状态、错误信息、`session_id`、下载地址
- `model` 为对象：`{ "providerID": "...", "modelID": "..." }`

4. `GET /jobs/{job_id}/events`
- SSE 输出任务事件
- 端点为 async 生成器，内部通过 `asyncio.to_thread` 调用同步仓储路径，避免阻塞事件循环

5. `POST /jobs/{job_id}/abort`
- 终止任务并进入 `aborted`

6. `GET /jobs/{job_id}/artifacts`
- 仅返回 `output` 与 `bundle` 类产物

7. `GET /jobs/{job_id}/download`
- 下载统一打包 `result.zip`

8. `GET /jobs/{job_id}/artifacts/{artifact_id}/download`
- 仅允许下载 `output`/`bundle` 分类文件

### 4.2 Skills API

- `GET /skills`
- `GET /skills/{skill_code}`

---

## 5. 状态机设计

状态枚举：

`created -> queued -> running -> waiting_approval -> verifying -> packaging -> succeeded | failed | aborted`

关键规则：

- `aborted` 为终态，后续不允许写回其他状态
- Worker 在执行关键节点前后都会检查是否已中止

---

## 6. 执行主流程（Worker）

1. 从 DB 加载 Job + 输入文件元数据
2. 置状态 `running`
3. 创建 OpenCode session，记录 `session_id`
4. 读取 `execution-plan.json`，构造 prompt，调用 `prompt_async`
5. 进入“事件订阅主路径 + 轮询补偿”循环直到会话 idle 或超时：
  - 订阅 OpenCode `/event`，按 `session_id` 过滤并落库 `session.*` / `permission.*` 事件
  - 遇到权限相关事件立即触发 permission 策略自动回复
  - 每 2 秒补偿轮询 `session/status` 与 `/permission`（断流/静默时兜底）
  - permission 堵塞时切换 `waiting_approval`，解除后恢复 `running`
6. 拉取最后一条消息并落盘 `logs/opencode-last-message.md`
7. 置 `verifying`：
  - 校验 `inputs/` 哈希未变化
  - 由 Skill 校验 `outputs/` 契约
8. 置 `packaging`：
  - 生成 `manifest.json`
  - 打包 `bundle/result.zip`
  - 回写 output/bundle/log 元数据
9. 成功置 `succeeded`；异常置 `failed`
10. 若任意节点检测到中止，进入 `aborted`

### 6.1 会话完成判定

- 主完成条件：`/session/status` 中目标 `session_id` 的 `type == "idle"`
- `type == "retry"` 作为事件记录，不直接判定失败
- 到达 soft timeout 后会尝试调用 `abort_session`，并抛出超时错误进入 `failed`

---

## 7. P1 设计决策（已落地）

### 7.1 幂等语义强一致

- 幂等命中条件：`tenant_id + idempotency_key + requirement_hash`
- `requirement_hash` 计算方式：
  - `requirement.strip()`
  - 每个上传文件的 `filename + sha256(content)`
- 避免“同 key 不同内容”误复用旧 Job

### 7.2 `aborted` 不可覆盖

- Repository 层禁止 `aborted -> 非aborted` 状态更新
- Executor 在关键步骤调用 `_ensure_not_aborted` 与 `_set_status_or_abort`

### 7.3 产物暴露最小化

- 列表与下载只开放 `output`、`bundle`
- 屏蔽 `input`、`log` 的外部下载路径

### 7.4 OpenCode `model` 契约对齐

- 内部统一用对象：
  - `providerID`
  - `modelID`
- 对外 API 入参拆为 `model_provider_id + model_id`
- DB 存储字段改为 `model_json`

### 7.5 连接复用与性能优先

- `OpenCodeClient` 复用进程级 `httpx.Client`（连接池 + keep-alive）
- `OpenCodeEventBridge` 复用进程级 `httpx.Client` 进行 SSE 连接
- 避免在高频路径（状态查询/权限轮询）反复创建短生命周期 HTTP 客户端

### 7.6 async 路径去阻塞

- `jobs` SSE 接口中的同步服务/DB 调用统一下沉到线程池执行（`asyncio.to_thread`）
- 避免 async 事件流中直接运行同步 I/O，减少事件循环阻塞风险

---

## 8. 数据模型

### 8.1 `jobs`

- `id`
- `tenant_id`
- `status`
- `session_id`
- `workspace_dir`
- `requirement_text`
- `selected_skill`
- `agent`
- `model_json`（JSON）
- `output_contract_json`
- `error_code` / `error_message`
- `created_by`
- `result_bundle_path`
- `created_at` / `updated_at`

### 8.2 `job_files`

- `id`
- `job_id`
- `category`（`input|output|bundle|log`）
- `relative_path`
- `mime_type`
- `size_bytes`
- `sha256`
- `created_at`

### 8.3 `job_events`

- `id`
- `job_id`
- `status`
- `source`
- `event_type`
- `message`
- `payload`
- `created_at`

### 8.4 `permission_actions`

- `id`
- `job_id`
- `request_id`
- `action`（`once|always|reject`）
- `actor`
- `created_at`

### 8.5 `idempotency_records`

- `tenant_id`
- `idempotency_key`
- `requirement_hash`
- `job_id`
- 唯一约束：`(tenant_id, idempotency_key, requirement_hash)`

---

## 9. 安全与稳态策略

### 9.1 上传安全

- 文件名规范化（防路径穿越）
- 单文件大小上限（默认 50MB）
- 空文件拒绝

### 9.2 执行安全

- 全部 OpenCode 调用携带 `directory`
- permission 自动策略：
  - 允许工作区内编辑
  - 拒绝工作区外路径
  - 拒绝高风险 shell token

### 9.3 超时与重试

- job soft/hard timeout：15m/20m
- permission wait timeout：120s
- OpenCode 瞬时连接错误重试 2 次（30s/120s）
- SSE 断流场景下自动退化到补偿轮询，保证状态可收敛

---

## 10. Skill 模块化设计

- `BaseSkill` 抽象接口：
  - `score`
  - `build_execution_plan`
  - `build_prompt`
  - `validate_outputs`
  - `artifact_manifest`
- `SkillRegistry` 管理技能实例
- `SkillRouter` 支持：
  - 手动 `skill_code` 覆盖
  - 自动评分路由
  - 低分回退 `general-default`

首发技能：

- `general-default`
- `data-analysis`
- `ppt`

---

## 11. 配置与运行

主要配置（`app/config.py`）：

- `DATABASE_URL`
- `REDIS_URL`
- `DATA_ROOT`
- `OPENCODE_BASE_URL`
- `OPENCODE_SERVER_USERNAME`
- `OPENCODE_SERVER_PASSWORD`
- `MAX_UPLOAD_FILE_SIZE_BYTES`
- `SKILL_FALLBACK_THRESHOLD`
- `JOB_SOFT_TIMEOUT_SECONDS`
- `JOB_HARD_TIMEOUT_SECONDS`

服务入口：

- API：`app/main.py`
- Worker：`app/worker/tasks.py`
- Celery 配置：`app/worker/celery_app.py`
- 依赖容器：`app/application/container.py`（含资源回收）

---

## 12. 测试与质量基线

当前已包含：

- `test_skill_router.py`
- `test_permission_policy.py`
- `test_p1_regressions.py`

P1 回归测试覆盖：

- `requirement_hash` 使用文件内容
- `aborted` 状态不可被覆盖
- artifacts 仅输出/打包可见与可下载

---

## 13. 非兼容说明（本版策略）

本版明确采用“直接最优设计”，不对旧字段与旧契约做兼容层：

- `jobs.model` 已替换为 `jobs.model_json`
- `POST /jobs` 不再接收单字符串 `model`
- 幂等唯一约束采用三元键，不再使用旧二元键

如需部署到已有旧库，建议重建数据库或执行一次性迁移脚本后再上线。
