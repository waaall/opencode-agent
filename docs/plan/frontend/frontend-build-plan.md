# OpenCode Orchestrator 前端构建计划

## Context

后端 FastAPI + Celery 编排服务已完成，提供 `/api/v1/*` REST API 和 SSE 事件流。前端需要对接这些 API，提供任务创建（文件上传+需求文本）、实时状态跟踪、产物预览与下载的完整用户体验。当前仓库无任何前端代码。

本项目为内部编排工具，不需要 SSR/SEO，采用纯 SPA 架构。

接口契约基线（与当前后端实现对齐）：

- 前端允许传 `skill_code`（可选），用于手动覆盖技能路由；不传时由后端自动路由。
- 产物接口只暴露 `output|bundle` 两类文件。
- 事件日志采用“最近 N 条内存窗口 + 前端分页”。

## 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 框架 | React ≥19.2 + TypeScript | 纯 SPA，无 SSR 需求 |
| 构建 | Vite 7 | 极速 HMR，Rollup 打包 |
| 组件库 | Ant Design 6 | 表格/表单/上传/步骤条等开箱即用 |
| 状态管理 | Zustand | 轻量全局 store，使用 selector + 事件窗口裁剪 |
| HTTP 客户端 | Axios | 拦截器统一错误处理/auth 注入 |
| 路由 | React Router 7 (`react-router-dom`) | BrowserRouter 场景最稳妥 |
| Markdown 预览 | react-markdown + remark-gfm | 懒加载 |
| 测试 | Vitest + Testing Library + Playwright | 单元/集成/E2E |

## 目录结构

```
frontend/
  vite.config.ts
  tsconfig.json
  package.json
  .env.development                # VITE_API_BASE=http://localhost:8000/api/v1
  .env.production
  index.html
  public/
  src/
    main.tsx                      # 入口：ReactDOM.createRoot
    App.tsx                       # 路由配置
    vite-env.d.ts

    api/
      client.ts                   # Axios 实例 + 拦截器
      jobs.ts                     # Job 相关 API
      skills.ts                   # Skill 相关 API
      types.ts                    # TypeScript 类型（镜像后端 Pydantic schema）

    stores/
      job-detail.ts               # 单任务详情 store（轮询 + SSE 事件）
      job-list.ts                 # 任务列表 store（分页 + 筛选）
      skill.ts                    # 技能列表 store

    hooks/
      use-job-events.ts           # SSE 连接管理 hook
      use-polling.ts              # 通用轮询 hook

    pages/
      dashboard/
        index.tsx                 # 首页工作台
        SkillCards.tsx             # 技能卡片网格
        RecentJobs.tsx            # 最近任务表格
      job-create/
        index.tsx                 # 新建任务页
        JobCreateForm.tsx         # Antd Form 表单主体
        SkillSelector.tsx         # 技能选择 Select
        FileUploadArea.tsx        # Antd Upload 拖拽区域
        ModelSelector.tsx         # 模型供应商+模型选择
      job-detail/
        index.tsx                 # 任务详情页
        JobStatusStepper.tsx      # Antd Steps 状态机步骤条
        JobEventLog.tsx           # SSE 事件日志列表
        ArtifactSection.tsx       # 产物区域容器
        ArtifactList.tsx          # 产物列表 Antd Table
        ArtifactPreview.tsx       # 按 MIME 懒加载预览
        DownloadSection.tsx       # 下载按钮组
      job-list/
        index.tsx                 # 任务历史页
        JobTable.tsx              # Antd Table + 分页
        StatusFilter.tsx          # Antd Tabs 状态筛选

    layouts/
      AppLayout.tsx               # Antd Layout：Header + Sider + Content
      Sider.tsx                   # 侧边导航

    utils/
      job-status.ts               # 状态枚举 → 颜色/标签/Steps 映射
      format.ts                   # 日期、文件大小格式化
      file-type.ts                # MIME → 预览策略映射

    constants/
      job-states.ts               # 状态机定义与顺序
      api.ts                      # 端点路径常量
```

## TypeScript 类型定义（镜像后端 schema）

```typescript
// src/api/types.ts

// 任务状态枚举，与后端 JobStatus 一一对应
export type JobStatus =
  | 'created' | 'queued' | 'running' | 'waiting_approval'
  | 'verifying' | 'packaging' | 'succeeded' | 'failed' | 'aborted';

export interface JobCreateRequest {
  requirement: string;
  files: File[];                 // 至少 1 个
  skill_code?: string;
  agent?: string;
  model_provider_id?: string;   // 与 model_id 必须同时提供
  model_id?: string;
  output_contract?: Record<string, unknown>;
  idempotency_key?: string;
}

export interface JobCreateResponse {
  job_id: string;
  status: string;
  selected_skill: string;
}

export interface JobStartResponse {
  job_id: string;
  status: string;
}

// model 为 { providerID, modelID } 或 null
export interface JobDetailResponse {
  job_id: string;
  status: JobStatus;
  session_id: string | null;
  selected_skill: string;
  agent: string;
  model: { providerID: string; modelID: string } | null;
  error_code: string | null;
  error_message: string | null;
  download_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobEvent {
  job_id: string;
  status: string | null;
  source: 'api' | 'worker' | 'opencode';
  event_type: string;
  message: string | null;
  payload: Record<string, unknown> | null;
  created_at: string | null;
}

export interface ArtifactItem {
  id: number;
  category: 'output' | 'bundle';
  relative_path: string;
  mime_type: string | null;
  size_bytes: number;
  sha256: string;
  created_at: string;
}

export interface ArtifactListResponse {
  job_id: string;
  artifacts: ArtifactItem[];
  bundle_ready: boolean;
}

export interface SkillResponse {
  code: string;
  name: string;
  aliases: string[];
  version: string;
  schema_version: string;
  description: string;
  task_type: string;
  sample_output_contract: Record<string, unknown> | null;
}
```

## API 客户端层

### client.ts — Axios 实例

```typescript
import axios from 'axios';
import { message } from 'antd';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE,
  timeout: 15_000,
});

const recentErrorMap = new Map<string, number>();
const ERROR_DEDUP_WINDOW_MS = 3000;

// 响应拦截器：统一错误提示（支持静默 + 去重，避免轮询错误风暴）
apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    const msg = error.response?.data?.detail ?? '请求失败';
    const status = error.response?.status ?? '网络错误';
    const silent = error.config?.headers?.['x-silent-error'] === '1';
    const dedupKey = `${status}:${msg}`;
    const now = Date.now();
    const lastTs = recentErrorMap.get(dedupKey) ?? 0;

    if (!silent && now - lastTs > ERROR_DEDUP_WINDOW_MS) {
      message.error(`${status}: ${msg}`);
      recentErrorMap.set(dedupKey, now);
    }
    return Promise.reject(error);
  },
);

// 预留 auth 注入点
// apiClient.interceptors.request.use((config) => {
//   config.headers.Authorization = `Bearer ${token}`;
//   return config;
// });

export default apiClient;
```

### jobs.ts — Job API

```typescript
import apiClient from './client';
import type { JobCreateRequest, JobCreateResponse, JobStartResponse,
  JobDetailResponse, ArtifactListResponse } from './types';

// 创建任务：multipart/form-data
export async function createJob(data: JobCreateRequest): Promise<JobCreateResponse> {
  if (data.files.length === 0) {
    throw new Error('至少上传 1 个文件');
  }

  const form = new FormData();
  form.append('requirement', data.requirement);
  data.files.forEach((f) => form.append('files', f));
  if (data.skill_code) form.append('skill_code', data.skill_code);
  if (data.agent) form.append('agent', data.agent);
  if (data.model_provider_id && data.model_id) {
    form.append('model_provider_id', data.model_provider_id);
    form.append('model_id', data.model_id);
  }
  if (data.output_contract) form.append('output_contract', JSON.stringify(data.output_contract));
  if (data.idempotency_key) form.append('idempotency_key', data.idempotency_key);

  const res = await apiClient.post<JobCreateResponse>('/jobs', form);
  return res.data;
}

export const startJob = (jobId: string) =>
  apiClient.post<JobStartResponse>(`/jobs/${jobId}/start`).then((r) => r.data);

export const getJob = (jobId: string, opts?: { silentError?: boolean }) =>
  apiClient.get<JobDetailResponse>(`/jobs/${jobId}`, {
    headers: opts?.silentError ? { 'x-silent-error': '1' } : undefined,
  }).then((r) => r.data);

export const abortJob = (jobId: string) =>
  apiClient.post<JobDetailResponse>(`/jobs/${jobId}/abort`).then((r) => r.data);

export const getArtifacts = (jobId: string) =>
  apiClient.get<ArtifactListResponse>(`/jobs/${jobId}/artifacts`).then((r) => r.data);

// 下载链接直接拼 URL，浏览器原生下载
export const bundleDownloadUrl = (jobId: string) =>
  `${import.meta.env.VITE_API_BASE}/jobs/${jobId}/download`;

export const artifactDownloadUrl = (jobId: string, artifactId: number) =>
  `${import.meta.env.VITE_API_BASE}/jobs/${jobId}/artifacts/${artifactId}/download`;
```

### skills.ts — Skill API

```typescript
import apiClient from './client';
import type { SkillResponse } from './types';

export const listSkills = (taskType?: string) =>
  apiClient.get<SkillResponse[]>('/skills', { params: taskType ? { task_type: taskType } : {} })
    .then((r) => r.data);

export const getSkill = (code: string) =>
  apiClient.get<SkillResponse>(`/skills/${code}`).then((r) => r.data);
```

## Zustand Store 设计

### job-detail.ts — 单任务详情 + SSE 事件

```typescript
import { create } from 'zustand';
import type { JobDetailResponse, JobEvent } from '@/api/types';

interface JobDetailStore {
  job: JobDetailResponse | null;
  events: JobEvent[]; // 仅保留最近 N 条
  eventPage: number;
  pageSize: number;
  sseStatus: 'idle' | 'connected' | 'error';

  // actions
  setJob: (job: JobDetailResponse) => void;
  appendEvents: (batch: JobEvent[]) => void;
  setEventPage: (page: number) => void;
  setSseStatus: (s: 'idle' | 'connected' | 'error') => void;
  reset: () => void;
}

const EVENT_WINDOW_LIMIT = 1000;
const EVENT_PAGE_SIZE = 50;

export const useJobDetailStore = create<JobDetailStore>((set) => ({
  job: null,
  events: [],
  eventPage: 1,
  pageSize: EVENT_PAGE_SIZE,
  sseStatus: 'idle',

  setJob: (job) => set({ job }),
  appendEvents: (batch) => set((s) => {
    const merged = [...s.events, ...batch];
    const nextEvents = merged.length > EVENT_WINDOW_LIMIT
      ? merged.slice(merged.length - EVENT_WINDOW_LIMIT)
      : merged;
    return { events: nextEvents };
  }),
  setEventPage: (eventPage) => set({ eventPage }),
  setSseStatus: (sseStatus) => set({ sseStatus }),
  reset: () => set({ job: null, events: [], eventPage: 1, pageSize: EVENT_PAGE_SIZE, sseStatus: 'idle' }),
}));
```

### skill.ts — 技能列表

```typescript
import { create } from 'zustand';
import type { SkillResponse } from '@/api/types';
import { listSkills } from '@/api/skills';

interface SkillStore {
  skills: SkillResponse[];
  loading: boolean;
  fetch: () => Promise<void>;
}

export const useSkillStore = create<SkillStore>((set, get) => ({
  skills: [],
  loading: false,
  fetch: async () => {
    if (get().skills.length > 0) return; // 已缓存则跳过
    set({ loading: true });
    const skills = await listSkills();
    set({ skills, loading: false });
  },
}));
```

## 核心 Hooks

### use-job-events.ts — SSE 连接管理

```typescript
import { startTransition, useEffect, useRef } from 'react';
import { useJobDetailStore } from '@/stores/job-detail';
import type { JobEvent } from '@/api/types';

const API_BASE = import.meta.env.VITE_API_BASE;
const MAX_BUFFER_EVENTS = 300;

export function useJobEvents(jobId: string | null, enabled: boolean) {
  const appendEvents = useJobDetailStore((s) => s.appendEvents);
  const setSseStatus = useJobDetailStore((s) => s.setSseStatus);
  // 用 ref 缓冲高频 SSE 数据，定时批量写入 store
  const bufferRef = useRef<JobEvent[]>([]);
  const retryRef = useRef(0);

  useEffect(() => {
    if (!jobId || !enabled) return;

    let es: EventSource | null = null;
    let disposed = false;
    let flushTimer: ReturnType<typeof setInterval> | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const pushEvent = (event: JobEvent) => {
      bufferRef.current.push(event);
      if (bufferRef.current.length > MAX_BUFFER_EVENTS) {
        bufferRef.current = bufferRef.current.slice(bufferRef.current.length - MAX_BUFFER_EVENTS);
      }
    };

    const flush = () => {
      if (bufferRef.current.length === 0) return;
      const batch = [...bufferRef.current];
      bufferRef.current = [];
      startTransition(() => {
        appendEvents(batch);
      });
    };

    const connect = () => {
      if (disposed) return;
      es = new EventSource(`${API_BASE}/jobs/${jobId}/events`);

      es.onopen = () => {
        setSseStatus('connected');
        retryRef.current = 0;
      };

      // onmessage 兜底接收所有事件
      es.onmessage = (e) => {
        try {
          pushEvent(JSON.parse(e.data));
        } catch { /* keep-alive */ }
      };

      // 已知事件类型通过 addEventListener 接收
      const knownTypes = [
        'skill.router.fallback', 'job.enqueued', 'opencode.prompt_async.sent',
        'session.updated', 'session.retry', 'permission.replied', 'job.failed',
      ];
      for (const type of knownTypes) {
        es.addEventListener(type, (e: MessageEvent) => {
          try { pushEvent(JSON.parse(e.data)); } catch { /* skip */ }
        });
      }

      es.onerror = () => {
        setSseStatus('error');
        es?.close();
        // 指数退避重连，最多 5 次
        if (retryRef.current < 5) {
          const delay = Math.min(1000 * 2 ** retryRef.current, 16_000);
          retryRef.current += 1;
          retryTimer = setTimeout(connect, delay);
        }
      };
    };

    connect();
    // 每 500ms 批量刷新到 store
    flushTimer = setInterval(flush, 500);

    return () => {
      disposed = true;
      es?.close();
      if (flushTimer) clearInterval(flushTimer);
      if (retryTimer) clearTimeout(retryTimer);
      flush();
    };
  }, [jobId, enabled, appendEvents, setSseStatus]);
}
```

### use-polling.ts — 通用轮询 hook

```typescript
import { useEffect, useRef } from 'react';

// 通用轮询：回调返回 true 时停止
export function usePolling(
  callback: () => Promise<boolean>, // 返回 true = 停止轮询
  interval: number,
  enabled: boolean,
) {
  const savedCallback = useRef(callback);
  savedCallback.current = callback;

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let inFlight = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      if (stopped || inFlight) return;
      inFlight = true;
      try {
        const shouldStop = await savedCallback.current();
        if (!stopped && !shouldStop) {
          timer = setTimeout(tick, interval);
        }
      } finally {
        inFlight = false;
      }
    };
    tick();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [interval, enabled]);
}
```

## 页面与 Antd 组件映射

### `/` 首页工作台

| 区域 | Antd 组件 |
|---|---|
| 技能卡片网格 | `Card` + `Row`/`Col` |
| 最近任务表格 | `Table` (columns: 任务ID、技能、状态、时间) |
| 新建任务入口 | `Button` type="primary" → 导航到 `/jobs/new` |

### `/jobs/new` 新建任务

| 区域 | Antd 组件 |
|---|---|
| 表单容器 | `Form` (layout="vertical") |
| 技能选择 | `Select` + `Form.Item`（可选，提交 `skill_code`） |
| 模型选择 | 两个 `Select`：供应商 + 模型 (`model_provider_id` / `model_id`) |
| 文件上传 | `Upload.Dragger` (multiple, 支持拖拽，至少 1 个文件) |
| 需求文本 | `Input.TextArea` |
| 提交 | `Button` type="primary" loading 状态 |

提交流程: `createJob()` → `startJob()` → `navigate('/jobs/{jobId}')`。

幂等键策略：

- 首次进入新建页时生成 `draft_idempotency_key` 并写入 `localStorage`。
- 用户点击“重试提交”时复用同一个 key，避免重复创建 Job。
- 成功创建并启动后清理该 key；用户点击“重置表单”时也清理并重新生成。
- `localStorage` key 带版本前缀（如 `oc:v1:job-create:idempotency-key`），便于后续升级迁移。

### `/jobs/:jobId` 任务详情

| 区域 | Antd 组件 |
|---|---|
| 状态步骤条 | `Steps` (items 由 job-states.ts 配置驱动) |
| 基本信息 | `Descriptions` (技能、agent、模型、创建时间) |
| SSE 事件日志 | `Timeline` + `Pagination`（只渲染最近 N 条中的当前页） |
| SSE 连接状态 | `Badge` status dot (green/orange/red) |
| 中止按钮 | `Popconfirm` + `Button` danger |
| 错误展示 | `Alert` type="error" (当 status=failed) |
| 产物列表 | `Table` (文件名、类型、大小、操作) |
| 产物预览 | `Modal` / 侧边 `Drawer`，按 MIME 懒加载渲染器 |
| 打包下载 | `Button` icon={DownloadOutlined} href=bundleDownloadUrl |

事件日志分页策略：

- store 只保留最近 `N=1000` 条事件（内存窗口）。
- 每页 `50` 条，默认展示最新页。
- 翻页只做前端切片，不触发额外网络请求。

```typescript
const events = useJobDetailStore((s) => s.events);
const page = useJobDetailStore((s) => s.eventPage);
const pageSize = useJobDetailStore((s) => s.pageSize);

const total = events.length;
const start = Math.max(total - page * pageSize, 0);
const end = total - (page - 1) * pageSize;
const visibleEvents = events.slice(start, end);
```

**状态机步骤条配置：**

```
created → queued → running → [waiting_approval] → verifying → packaging → succeeded
                                                                        ↘ failed
                                                                        ↘ aborted
```

### `/jobs` 任务历史

| 区域 | Antd 组件 |
|---|---|
| 状态筛选 | `Tabs` (全部/运行中/已完成/失败) |
| 任务表格 | `Table` + 分页 (pagination prop) |
| 状态徽章 | `Tag` color 由 job-status.ts 配置映射 |

## Vite 配置

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    port: 3000,
    // 开发环境代理后端 API，避免 CORS
    proxy: {
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // 分包：antd + react 独立 chunk
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-antd': ['antd', '@ant-design/icons'],
        },
      },
    },
  },
});
```

环境变量：

```bash
# .env.development — 开发环境走 Vite proxy，baseURL 用相对路径
VITE_API_BASE=/api/v1

# .env.production — 生产环境按实际部署地址配置
VITE_API_BASE=https://api.example.com/api/v1
```

## React Router 路由

```typescript
// src/App.tsx
import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import AppLayout from '@/layouts/AppLayout';

// 懒加载页面，拆分 chunk
const Dashboard = lazy(() => import('@/pages/dashboard'));
const JobCreate = lazy(() => import('@/pages/job-create'));
const JobDetail = lazy(() => import('@/pages/job-detail'));
const JobList   = lazy(() => import('@/pages/job-list'));

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Suspense fallback={null}><Dashboard /></Suspense>} />
          <Route path="jobs" element={<Suspense fallback={null}><JobList /></Suspense>} />
          <Route path="jobs/new" element={<Suspense fallback={null}><JobCreate /></Suspense>} />
          <Route path="jobs/:jobId" element={<Suspense fallback={null}><JobDetail /></Suspense>} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

## 实施阶段

### Phase 1 — 基础骨架 (2 天)
1. `npm create vite@latest frontend -- --template react-ts` 初始化
2. 安装依赖：`antd`, `@ant-design/icons`, `zustand`, `axios`, `react-router-dom`
3. 配置 `vite.config.ts` (alias, proxy, 分包)
4. 实现 `src/api/types.ts` — 全部 TypeScript 类型
5. 实现 `src/api/client.ts` — Axios 实例 + 拦截器
6. 实现 `src/api/jobs.ts` + `src/api/skills.ts`
7. 构建 `AppLayout` (Antd Layout + Sider + Header)
8. 配置 React Router 路由

### Phase 2 — 任务创建流程 (3 天)
1. `useSkillStore` + `skill.ts` store
2. `SkillSelector` (Antd Select)
3. `FileUploadArea` (Antd Upload.Dragger)
4. `ModelSelector` (两个级联 Select: provider + model)
5. `JobCreateForm` (Antd Form + 校验规则：`files.length >= 1`)
6. `/jobs/new` 页面组装
7. 实现幂等键管理（草稿级 localStorage 复用，成功后清理）
8. 对接 `createJob` → `startJob` → navigate 详情页

### Phase 3 — 任务详情 + SSE (3 天)
1. `useJobDetailStore` — Zustand store
2. `useJobEvents` — SSE hook (ref 缓冲 + 500ms 批量写 store + 安全重连清理)
3. `usePolling` — 轮询 `getJob({ silentError: true })`，终态自动停止
4. `JobStatusStepper` (Antd Steps，由状态配置驱动)
5. `JobEventLog` (Antd Timeline + Pagination，最近 N 条窗口内分页)
6. 中止：`Popconfirm` + `abortJob()`
7. `/jobs/:jobId` 页面组装

### Phase 4 — 产物与下载 (2 天)
1. `ArtifactList` (Antd Table)
2. `ArtifactPreview` — 按 MIME 懒加载：
   - `text/markdown` → `react-markdown` (lazy import)
   - `image/*` → `<img>` / Antd Image
   - 其他 → 文件图标 + 元信息
3. `DownloadSection` — 打包下载 + 单文件下载按钮

### Phase 5 — 工作台 + 历史 (2 天)
1. 首页 `SkillCards` + `RecentJobs`
2. `/jobs` 页 `JobTable` + `StatusFilter` (Antd Tabs)
3. 分页 (Antd Table pagination)

### Phase 6 — 打磨与测试 (3 天)
1. 全局 Error Boundary
2. 空状态 (Antd Empty)
3. 响应式：Antd Grid breakpoint 适配
4. Vitest 单元测试 (stores, API, utils)
5. Playwright E2E (创建→监控→下载完整流程)

## 验证方式

1. **开发环境**: `npm run dev` + 后端 `docker-compose up` 联调
2. **API 对接**: Vite proxy 转发 `/api/v1` 到后端
3. **SSE 验证**: 创建任务后在详情页观察 Timeline 实时更新 + Badge 连接状态
4. **打包验证**: `npm run build && npx vite preview` 检查分包，确认懒加载生效
5. **单元测试**: `npx vitest` — store 逻辑、API 调用、工具函数
6. **E2E 测试**: `npx playwright test` — 完整用户流程

## 部署

SPA 纯静态产物，生产部署只需 nginx：

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # SPA history fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 反代后端 API
    location /api/v1/ {
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        # SSE 需要关闭缓冲
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
    }
}
```

也可直接加入现有 `docker-compose.yml` 作为 `web` 服务。

## 前置依赖

- 后端需补充 `GET /api/v1/jobs` 列表端点（支持分页、状态筛选），供任务历史页和首页最近任务使用

## 风险与应对

| 风险 | 应对 |
|---|---|
| SSE 未知 event_type | `onmessage` 兜底 + console.warn 日志 |
| SSE 高频事件导致内存增长 | store 只保留最近 `N=1000` 条，分页渲染 |
| SSE 重连定时器泄漏 | cleanup 中统一 `clearTimeout/clearInterval` |
| 轮询错误提示刷屏 | 轮询请求使用 `x-silent-error`，拦截器错误去重 |
| 大文件上传超时 | Axios `onUploadProgress` 回调显示进度条 |
| PPTX 预览包体积大 | React.lazy 懒加载 + 点击才加载预览器 |
| v1 无鉴权 | Axios 拦截器预留 auth header 注入点 |
| Antd 包体积 | Vite 自动 tree-shaking + manualChunks 独立分包 |
