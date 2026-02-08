# 前端整体设计


## 子应用双模式设计（Standalone / Portal）

### 1. 设计目标

同一套代码同时支持两种运行方式：

| 模式 | 场景 | 特征 |
|---|---|---|
| **Standalone** | `npm run dev` 或独立部署 | 完整 UI（含顶部导航），根路径 `/` 访问 |
| **Portal** | 被统一入口通过 iframe 嵌入 | 仅保留业务项 Header（全局项由 Portal 头部承载），子路径 `/apps/<app>/` 访问 |

切换模式仅需更改环境变量，无代码分支。

---

### 2. 环境变量

所有变量均以 `VITE_` 开头，Vite 构建时静态注入，运行时通过 `import.meta.env` 读取。

| 变量 | 含义 | Standalone 默认值 | Portal 示例值 |
|---|---|---|---|
| `VITE_BASE_PATH` | Vite `base`，控制构建产物资源前缀 | `/` | `/apps/agents/` |
| `VITE_ROUTER_BASENAME` | React Router `basename`（预留） | `/` | `/apps/agents` |
| `VITE_EMBEDDED` | 是否以嵌入模式运行 | `false` | `true` |
| `VITE_STORAGE_NS` | localStorage / sessionStorage 命名空间 | `agents` | `agents` |
| `VITE_COOKIE_PATH` | Cookie 的 `Path` 属性 | `/` | `/apps/agents/` |

TypeScript 类型声明见 `src/vite-env.d.ts`。