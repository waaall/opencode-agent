# OpenCode Orchestrator 前端构建计划 v2

## 1. Context & Goals

本文件是前端构建计划 v2，目标是在不改后端 API 的前提下，把 v1 升级为可直接实施的双模式方案。

v1 参考文档：

- `docs/plan/frontend/frontend-build-plan.md`

v2 目标：

1. 同一套代码支持 `Standalone` 与 `Portal` 两种运行模式，切换只依赖环境变量。
2. UI 视觉升级，建立可扩展 Design System，支持明暗主题。
3. 参数配置化，减少硬编码，统一由 `app-config.ts` 管理。
4. 主题默认跟随系统，Portal 模式可跟随父容器主题消息。
5. 保持前端性能基线，对齐 `vercel-react-best-practices` 关键规则。

非目标：

1. 不新增后端业务接口。
2. 不引入 SSR。
3. 不拆分为两套前端工程。

## 2. Dual-Mode Architecture (Standalone / Portal)

### 2.1 模式定义

| 模式 | 场景 | 路径 | UI 壳层 |
|---|---|---|---|
| `Standalone` | 本地开发/独立部署 | `/` | 完整壳层（全局 Header + Sider + Content） |
| `Portal` | 由统一入口 iframe 嵌入 | `/apps/<app>/` | 仅业务 Header + Content（不渲染全局 Header/Sider） |

### 2.2 运行时判定

1. `VITE_EMBEDDED=true` 时为 `Portal`。
2. 其他值为 `Standalone`。
3. 判定只在 `src/config/app-config.ts` 执行一次，业务组件只读取 `config.mode`。

### 2.3 壳层组件职责

1. `AppShell`：统一入口，按 `mode` 选择渲染壳层。
2. `StandaloneShell`：挂载全局导航、业务路由容器、主题容器。
3. `PortalShell`：仅挂载业务 Header 与业务路由容器。
4. 页面组件不感知模式差异，模式差异仅体现在壳层和路由基路径。

## 3. Runtime Config & Env Contract

### 3.1 中心配置原则

1. 所有可变参数必须来自 `import.meta.env` 并由 `app-config.ts` 解析。
2. 禁止在业务代码中直接写裸常量（例如超时、重试次数、窗口大小、路径前缀）。
3. 配置解析必须具备容错与默认值回退。

### 3.2 关键类型

```ts
export type AppMode = 'standalone' | 'portal';
export type Theme = 'light' | 'dark';

export interface AppRuntimeConfig {
  mode: AppMode;
  basePath: string;
  routerBasename: string;
  embedded: boolean;
  storageNs: string;
  cookiePath: string;
  apiBase: string;
  apiTimeoutMs: number;
  errorDedupWindowMs: number;
  eventWindowLimit: number;
  eventPageSize: number;
  sseFlushIntervalMs: number;
  sseRetryMax: number;
  sseRetryBaseMs: number;
  sseRetryMaxMs: number;
  portalAllowedOrigins: string[];
}
```

### 3.3 环境变量契约

| 变量 | 含义 | Standalone 默认值 | Portal 示例值 |
|---|---|---|---|
| `VITE_BASE_PATH` | Vite `base`（资源前缀） | `/` | `/apps/agents/` |
| `VITE_ROUTER_BASENAME` | React Router `basename` | `/` | `/apps/agents` |
| `VITE_EMBEDDED` | 是否嵌入模式 | `false` | `true` |
| `VITE_STORAGE_NS` | Storage 命名空间 | `agents` | `agents` |
| `VITE_COOKIE_PATH` | Cookie Path | `/` | `/apps/agents/` |
| `VITE_API_BASE` | API 基础路径 | `/api/v1` | `/api/v1` |
| `VITE_PORTAL_ALLOWED_ORIGINS` | Portal 消息来源白名单（逗号分隔） | `` | `https://portal.example.com` |
| `VITE_API_TIMEOUT_MS` | Axios 超时 | `15000` | `15000` |
| `VITE_ERROR_DEDUP_WINDOW_MS` | 错误提示去重窗口 | `3000` | `3000` |
| `VITE_EVENT_WINDOW_LIMIT` | 事件内存窗口上限 | `1000` | `1000` |
| `VITE_EVENT_PAGE_SIZE` | 事件分页大小 | `50` | `50` |
| `VITE_SSE_FLUSH_INTERVAL_MS` | SSE 批量刷新间隔 | `500` | `500` |
| `VITE_SSE_RETRY_MAX` | SSE 最大重试次数 | `5` | `5` |
| `VITE_SSE_RETRY_BASE_MS` | SSE 指数退避起始 | `1000` | `1000` |
| `VITE_SSE_RETRY_MAX_MS` | SSE 指数退避上限 | `16000` | `16000` |

### 3.4 解析与规范化规则

1. `basePath` 必须以 `/` 开头且以 `/` 结尾。
2. `routerBasename` 必须以 `/` 开头，根路径除外不以 `/` 结尾。
3. 数值变量解析失败时回退默认值并打印 warning（仅开发环境）。
4. `portalAllowedOrigins` 解析为空数组时，Portal 主题同步进入安全降级模式（仅使用系统主题）。

## 4. Theme System (System + Portal Sync)

### 4.1 主题来源优先级

1. `Portal` 模式且收到合法 Portal 主题消息：使用 `portal`。
2. 未收到合法 Portal 消息或消息超时：回退 `system`。
3. `Standalone` 模式：始终使用 `system`。

### 4.2 Portal 通信协议

子应用发送：

```ts
type PortalReadyOutboundMessage = {
  type: 'agents.child.ready';
  source: 'agents-app';
  payload: { version: '1.0'; capabilities: ['theme'] };
};
```

Portal 发送：

```ts
type PortalThemeInboundMessage = {
  type: 'portal.theme.set';
  source: 'portal-shell';
  payload: { theme: 'light' | 'dark' };
};
```

### 4.3 安全策略

1. 仅接收 `origin` 命中 `VITE_PORTAL_ALLOWED_ORIGINS` 的消息。
2. 对 `type/source/payload` 做结构校验，非法消息直接丢弃。
3. 不接受白名单外消息，不进行弱校验兼容。

### 4.4 实现约束

1. 主题最终落到 `html[data-theme='light|dark']`。
2. Ant Design 通过 `ConfigProvider` 读取同一主题状态。
3. 所有主题 token 从 `src/theme/tokens.ts` 导出，页面不直写颜色字面量。
4. 监听器在组件卸载时必须清理，避免重复订阅。

## 5. UI/Design System & Visual Upgrade

### 5.1 视觉方向

1. 风格：轻质玻璃层 + 清晰信息层级 + 强状态可读性。
2. 主色：蓝绿科技色系，避免默认紫色方案。
3. 暗色：保证状态对比度与可读性，不依赖纯黑背景。

### 5.2 Token 体系

1. `color`：品牌色、语义色、背景色、边框色、文字色。
2. `radius`：4/8/12/16 四档圆角。
3. `shadow`：轻/中/重三档阴影。
4. `spacing`：4/8/12/16/24/32 统一间距尺度。
5. `motion`：`120ms/180ms/240ms` 三档时长和统一 easing。

### 5.3 页面级美化要求

1. Dashboard 引入层次化背景与卡片信息分区。
2. Job Detail 的状态区、事件区、产物区分块可视层级明确。
3. 表格与列表统一 hover、selected、disabled 视觉反馈。
4. 状态色（`running/succeeded/failed/aborted`）使用语义 token，不可直接写 hex。

### 5.4 组件约束

1. `AppLayout` 仅负责结构，不含业务样式。
2. `BusinessHeader` 同时适配 Standalone/Portal，内容一致，外围装饰可因模式调整。
3. `StatusBadge` 与 `JobStatusStepper` 必须共享同一状态色映射源。

## 6. Routing / Build / Deployment Rules

### 6.1 路由规则

1. `BrowserRouter` 必须使用 `basename={config.routerBasename}`。
2. 所有内部跳转使用相对路由或 `generatePath`，避免拼接硬编码路径。

### 6.2 构建规则

1. Vite `base` 使用 `config.basePath`。
2. 保留现有手动分包，并把重组件保持懒加载。
3. 禁止在代码中硬编码 `/api/v1`、`/apps/agents/` 等路径常量。

### 6.3 部署规则

1. Standalone 与 Portal 可共享同一构建产物，仅通过环境变量区分。
2. Nginx 必须保留 SPA fallback 与 SSE 禁缓冲配置。
3. Cookie Path 使用 `VITE_COOKIE_PATH`，避免 Portal 子路径污染全局 Cookie。

## 7. Performance Baseline (Vercel React Best Practices Mapping)

| 规则 | 在本项目的落地要求 |
|---|---|
| `bundle-dynamic-imports` | 产物预览器与重量级页面按需加载 |
| `bundle-conditional` | Standalone 专属壳层/Portal 专属桥接逻辑按模式条件加载 |
| `client-event-listeners` | `message`/`matchMedia` 监听器单实例、可清理 |
| `client-localstorage-schema` | 使用 `VITE_STORAGE_NS` + 版本化 key（例如 `oc:v1:*`） |
| `rerender-transitions` | 高频 SSE 写入使用 `startTransition` |
| `rerender-dependencies` | Zustand 使用 selector 订阅，避免全量订阅触发重渲染 |

补充性能约束：

1. 事件列表固定窗口 `eventWindowLimit`，不做无限累积。
2. 轮询与 SSE 重试参数全部配置化，便于按环境调优。

## 8. Implementation Phases

### Phase A：配置中心与模式判定

1. 新增 `src/config/app-config.ts`、`src/config/env.ts`。
2. 完成环境变量解析、默认值、路径规范化、白名单解析。
3. 输出 `AppRuntimeConfig` 单例。

### Phase B：双模式壳层与路由 basename/base

1. 新增 `AppShell`、`StandaloneShell`、`PortalShell`。
2. Router 接入 `basename`。
3. Vite 配置读取 `basePath`。

### Phase C：主题系统与 Portal 协议

1. 新增主题 store 与 token 映射。
2. 完成系统主题监听。
3. 完成 Portal 握手与主题消息接收。
4. 加入 `origin` 白名单校验。

### Phase D：视觉 token 化与页面美化

1. 建立 `theme/tokens.ts` 与语义映射。
2. 重构核心页面为 token 驱动样式。
3. 统一状态组件视觉规范。

### Phase E：性能与稳定性收敛

1. 把 SSE、轮询、错误去重参数接入配置中心。
2. 检查 selector 订阅、监听器清理、懒加载边界。
3. 做一次 bundle 与重渲染热点审查。

### Phase F：联调、验收、发布检查

1. Standalone 联调与 Portal 联调。
2. 验收用例逐条执行。
3. 输出发布前配置模板与回滚说明。

## 9. Testing & Acceptance

### 9.1 必测场景

1. Standalone 根路径访问，完整壳层可见。
2. Portal 子路径访问，仅业务 Header 可见。
3. 系统主题切换后 UI 自动切换。
4. Portal 发送主题消息后子应用即时切换。
5. 非白名单 `origin` 消息被拒收且不改主题。
6. Portal 未发送主题时子应用回退系统主题。
7. 环境变量非法值时回退默认且应用不崩溃。
8. SSE 高频下事件窗口上限与分页策略生效。
9. 打包后资源前缀与路由 basename 正确。
10. 任务创建、状态跟踪、下载流程回归通过。

### 9.2 测试分层

1. 单元测试：配置解析、主题 reducer、消息校验器。
2. 组件测试：`AppShell` 模式分支与主题切换渲染。
3. E2E：Standalone 与 Portal 两条主流程。

## 10. Risks & Mitigations

| 风险 | 影响 | 应对 |
|---|---|---|
| Portal 与子应用跨域消息异常 | 主题无法同步 | 白名单 + 协议校验 + 系统主题回退 |
| 路径配置错误导致资源 404 | Portal 部署不可用 | 路径 normalize + 构建前校验 |
| 常量散落回潮 | 运维调参成本高 | 代码评审强制检查“只读配置中心” |
| 暗色对比不足 | 可读性下降 | 语义 token 对比度验收 |
| 高频事件导致性能抖动 | 页面卡顿 | 事件窗口 + startTransition + selector |

## 11. Assumptions

1. 当前会话没有可用 `frontend-design` skill，视觉方案由本文档内 Design System 指定。
2. 不新增后端 API，仅新增前端与 Portal 的消息契约。
3. 文档以中文编写，与现有项目文档风格一致。
4. 本次交付是 v2 设计文档落盘，不包含业务代码实现。
