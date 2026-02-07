# 企业级 Agent Orchestrator 实施方案（FastAPI + OpenCode + Skill 模块化）

## 概要

基于现有文档：

- `docs/api/opencode-server.md`
- `docs/demand/overall-damand.md`
- `docs/plan/initial/overall-design-plan.md`

第一版采用“共享 OpenCode 实例 + 工作目录隔离”的企业级编排架构。核心目标是把“输入需求 + 上传文件 + 选择/自动路由 Skill + 异步执行 + 产物下载”固化为统一流水线，后续新增 Skill 不改主流程，只加插件模块。

## 1. 已锁定决策

- OpenCode 隔离策略：共享实例，按 `directory` query 参数隔离目录
- 编排基础设施：Postgres + Redis + Celery
- 租户模型：单租户上线，数据模型预留多租户字段
- Skill 选择：后端自动路由，前端可手动覆盖 `skill_code`
- 产物存储：本地磁盘（工作区 + zip）
- 权限处理：策略自动批准（白名单）+ 非白名单拒绝
- 首版部署：Docker Compose
- 容量档位：T2（100 并发 job 目标）

## 2. 目标代码结构（可直接落仓）

| 路径 | 作用 |
|---|---|
| `services/orchestrator/app/main.py` | FastAPI 入口 |
| `services/orchestrator/app/api/v1/jobs.py` | Job API |
| `services/orchestrator/app/api/v1/skills.py` | Skill 列表/详情 API |
| `services/orchestrator/app/domain/models.py` | Job/Artifact/Event 领域模型 |
| `services/orchestrator/app/domain/enums.py` | 状态机与事件枚举 |
| `services/orchestrator/app/domain/skills/base.py` | Skill 基类 |
| `services/orchestrator/app/domain/skills/router.py` | Skill 自动路由 |
| `services/orchestrator/app/domain/skills/registry.py` | Skill 注册中心 |
| `services/orchestrator/app/application/orchestrator.py` | 编排总入口（创建/启动/终止） |
| `services/orchestrator/app/application/executor.py` | 单 Job 执行器 |
| `services/orchestrator/app/infra/opencode/client.py` | OpenCode API 封装 |
| `services/orchestrator/app/infra/opencode/event_bridge.py` | SSE 事件桥接 |
| `services/orchestrator/app/infra/storage/workspace.py` | 工作区管理 |
| `services/orchestrator/app/infra/storage/artifact.py` | 产物清单与 zip |
| `services/orchestrator/app/infra/security/permission_policy.py` | permission 自动处理策略 |
| `services/orchestrator/app/worker/celery_app.py` | Celery 配置 |
| `services/orchestrator/app/worker/tasks.py` | 执行任务/重试任务 |
| `services/orchestrator/migrations/*.sql` | 数据库 DDL |
| `apps/portal/src/pages/new-job.tsx` | 前端提交页（需求+文件+skill） |
| `apps/portal/src/pages/job-detail.tsx` | 前端执行详情与下载页 |
| `deploy/docker-compose.yml` | 首版部署编排 |

## 3. 公共 API/接口/类型（新增与定稿）

### 3.1 FastAPI 对外 API

| 方法 | 路径 | 关键字段 | 说明 |
|---|---|---|---|
| POST | `/api/v1/jobs` | `requirement`, `files[]`, `skill_code?`, `agent?`, `model?`, `output_contract?`, `idempotency_key` | 创建 job 与工作区 |
| POST | `/api/v1/jobs/{job_id}/start` | 无 | 入队执行 |
| GET | `/api/v1/jobs/{job_id}` | 无 | 状态、session、错误、产物摘要 |
| GET | `/api/v1/jobs/{job_id}/events` | SSE | 标准化状态流 |
| POST | `/api/v1/jobs/{job_id}/abort` | 无 | 终止任务 |
| GET | `/api/v1/jobs/{job_id}/artifacts` | 无 | 产物列表 |
| GET | `/api/v1/jobs/{job_id}/download` | 无 | 下载 `result.zip` |
| GET | `/api/v1/skills` | `task_type?` | 前端技能选择器 |
| GET | `/api/v1/skills/{skill_code}` | 无 | 技能元数据与输出契约 |

### 3.2 OpenCode 适配接口（内部）

- `GET /global/health`
- `POST /session`
- `POST /session/{sessionID}/prompt_async`
- `GET /event`
- `GET /session/status`
- `POST /permission/{requestID}/reply`
- `GET /session/{sessionID}/message?limit=1`
- `GET /file?path=...`
- `GET /file/content?path=...`

所有请求统一加 query 参数：`directory=/data/opencode-jobs/{job_id}`。

### 3.3 关键类型（固定）

```python
# domain/enums.py
class JobStatus(str, Enum):
    created = "created"
    queued = "queued"
    running = "running"
    waiting_approval = "waiting_approval"
    verifying = "verifying"
    packaging = "packaging"
    succeeded = "succeeded"
    failed = "failed"
    aborted = "aborted"

# domain/models.py
@dataclass
class JobContext:
    job_id: str
    tenant_id: str
    requirement: str
    workspace_dir: Path
    input_files: list[Path]
    selected_skill: str
    agent: str
    model: str | None
    output_contract: dict[str, Any] | None
```

## 4. Skill 模块化设计（基类 + 路由 + 插件）

### 4.1 Skill 基类（核心）

```python
# domain/skills/base.py
class BaseSkill(ABC):
    code: str
    name: str
    aliases: tuple[str, ...]
    version: str

    @abstractmethod
    def score(self, requirement: str, files: list[Path]) -> float:
        """0~1，自动路由评分"""

    @abstractmethod
    def build_execution_plan(self, ctx: JobContext) -> dict[str, Any]:
        """生成 execution-plan.json"""

    @abstractmethod
    def build_prompt(self, ctx: JobContext, plan: dict[str, Any]) -> str:
        """输出发送到 OpenCode 的最终 prompt"""

    @abstractmethod
    def validate_outputs(self, ctx: JobContext) -> None:
        """校验 outputs 是否满足契约，不满足抛异常"""

    @abstractmethod
    def artifact_manifest(self, ctx: JobContext) -> list[dict[str, Any]]:
        """返回产物清单"""
```

### 4.2 路由规则（无歧义）

- 若前端传 `skill_code`，直接校验并绑定该 Skill
- 若未传 `skill_code`，由 `SkillRouter` 对所有 Skill 执行 `score()`，取最高分
- 若最高分低于阈值 `0.45`，回退到 `general-default` Skill，并在 `job_events` 记录降级原因
- `execution-plan.json` 必含：`selected_skill`, `output_contract`, `packaging_rules`, `timeouts`, `retry_policy`

### 4.3 Skill 扩展规范

- 新增 Skill 只需新增一个 Python 模块并在 `registry.py` 注册
- Skill 不直接操作数据库或队列，只返回“计划与校验规则”
- 每个 Skill 必须携带 `schema_version`，便于后续兼容升级

## 5. 端到端执行流程（定稿）

1. `POST /jobs`：保存上传文件到 `inputs/`，写入 `job/request.md`，路由 Skill，写 `job/execution-plan.json`
2. `POST /jobs/{id}/start`：写状态 `queued`，投递 Celery
3. Worker 执行：创建 OpenCode session
4. 组装 prompt 并调用 `prompt_async`
5. 订阅 `/event`，按 `session_id` 过滤
6. 遇到 `permission.asked`，交由 `PermissionPolicyEngine` 自动回复
7. 定时轮询 `session/status`，当 session idle 切到 `verifying`
8. 调 Skill 的 `validate_outputs()`
9. 生成 `manifest.json` 并打包 `bundle/result.zip`
10. 状态更新为 `succeeded` 或 `failed`，SSE 推送结果
11. `GET /download` 返回统一包；前端支持单文件下载

## 6. 高性能与高可靠设计（T2 档）

- API：`uvicorn` 4 workers，单 worker async
- Celery：8 worker 进程，`concurrency=12`，总活跃槽位约 96
- 队列：`high`, `default`, `low`, `maintenance` 四队列
- DB 连接池：总 40（API 20 + Worker 20）
- 超时：job soft 15 分钟，hard 20 分钟
- 重试：仅瞬时错误重试 2 次，退避 30s/120s
- 幂等：`idempotency_key + tenant_id + requirement_hash` 唯一约束
- 断线恢复：`/event` 自动重连 + session 状态补偿轮询
- 故障降级：OpenCode 不可用时阻止新 job start，保留 created/queued
- 清理任务：定时清理过期 workspace、zip、临时日志

## 7. 安全设计

- OpenCode 强制 Basic Auth，内网通信
- 严格校验上传文件名并防止路径穿越
- `inputs/` 只读约束写入 prompt；验收时校验输入 hash 未变化
- permission 自动策略：
  - 允许 workspace 内编辑类权限
  - 拒绝外部目录访问与高风险 shell
  - 全量审计 `request_id`, `permission_id`, `decision`
- 预留字段：`tenant_id`, `created_by`, `trace_id`, `request_ip`

## 8. 数据库模型（第一版）

- `jobs`：主状态、session、skill、错误、时间戳、tenant 字段
- `job_files`：输入/输出/打包/日志文件元数据（sha256、size、mime）
- `job_events`：状态流与原始 OpenCode 事件映射
- `permission_actions`：自动或人工审批轨迹
- `idempotency_records`：防重复创建/启动

索引：

- `jobs(status, created_at desc)`
- `jobs(tenant_id, created_at desc)`
- `job_events(job_id, created_at)`
- `job_files(job_id, category)`

## 9. 前端交互（满足“打字 + 上传 + 选 skill”）

- 新建任务页：`requirement` 文本框、文件上传、`skill_code` 下拉（含“自动路由”）
- 执行详情页：状态时间线、SSE 实时日志、产物清单、下载按钮
- 失败可视化：显示错误码、最后一步、可重试入口
- 表单与 API 契约一致，不透出 OpenCode 内部细节

## 10. 测试与验收场景（必须覆盖）

单元测试：

- `SkillRouter` 覆盖“自动路由/手动覆盖/低置信回退”
- `BaseSkill.validate_outputs()` 契约校验
- permission 策略“允许/拒绝/超时”

集成测试：

- FastAPI + Celery + Redis + Postgres + mock OpenCode
- 全流程 `create -> start -> running -> succeeded`
- 异常流程 `OpenCode timeout -> retry -> failed`

E2E 测试：

- 上传 CSV，输出 `report.md + 图表`
- 上传素材图，输出 `slides.pptx`

性能测试（T2）：

- 100 并发 job 压测，目标成功率 >= 99%
- `POST /jobs` p95 < 300ms（不含文件流式上传时间）

回归与混沌：

- Redis 重启、OpenCode 短断连、Worker 异常退出后可恢复

验收门槛：

- 全链路可追踪 `job_id + session_id + request_id`
- 产物包完整，manifest hash 可校验

## 11. Docker Compose 交付清单

- 服务：`api`, `worker`, `beat`, `postgres`, `redis`, `opencode`, `nginx(optional)`
- 共享卷：`/data/opencode-jobs`（api/worker/opencode 共享）
- 环境变量：`OPENCODE_BASE_URL`, `OPENCODE_SERVER_USERNAME`, `OPENCODE_SERVER_PASSWORD`, `DATABASE_URL`, `REDIS_URL`
- 健康检查：`api /healthz`，`opencode /global/health`
- 启动顺序：DB/Redis -> OpenCode -> API/Worker

## 12. 实施里程碑（可执行）

1. M1（2-3 天）：项目骨架、DDL、Job API、workspace 管理
2. M2（2-3 天）：OpenCode client、event bridge、executor、状态机
3. M3（2 天）：Skill 基类、router、data-analysis 与 ppt 两个首发 Skill
4. M4（2 天）：artifact 打包、manifest、下载接口、权限策略
5. M5（2 天）：前端新建页/详情页、SSE 可视化
6. M6（2 天）：性能调优、混沌测试、Compose 部署文档

## 13. 显式假设与默认值

- OpenCode 协议以 `docs/api/opencode-server.md` 与 `docs/api/opencode-api.json` 为准
- 第一版不做对象存储，全部本地磁盘
- 第一版默认单租户运行，但所有主表保留 `tenant_id`
- 默认 agent 为 `build`，模型可空（由 OpenCode 默认模型决定）
- 默认自动路由 skill，前端可手动覆盖
- 不引入 MCP 作为首版依赖，后续通过 Skill 扩展接入
