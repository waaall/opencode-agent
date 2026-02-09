import {
  envString,
  envInt,
  envBool,
  normBasePath,
  normRouterBasename,
  normApiBaseUrl,
} from './env';

export type AppMode = 'standalone' | 'portal';
export type Theme = 'light' | 'dark';
export type ThemeMode = 'system' | Theme;

export interface AppRuntimeConfig {
  mode: AppMode;
  basePath: string;
  routerBasename: string;
  embedded: boolean;
  storageNs: string;
  cookiePath: string;
  apiBaseUrl: string;
  apiTimeoutMs: number;
  errorDedupWindowMs: number;
  eventWindowLimit: number;
  eventPageSize: number;
  sseBufferMax: number;
  sseFlushIntervalMs: number;
  sseRetryMax: number;
  sseRetryBaseMs: number;
  sseRetryMaxMs: number;
}

let _instance: AppRuntimeConfig | null = null;

/** 应用启动时调用一次，解析所有环境变量并生成配置单例 */
export function initConfig(): AppRuntimeConfig {
  if (_instance) return _instance;

  const embedded = envBool('VITE_EMBEDDED', false);
  const mode: AppMode = embedded ? 'portal' : 'standalone';

  _instance = {
    mode,
    basePath: normBasePath(envString('VITE_BASE_PATH', '/')),
    routerBasename: normRouterBasename(envString('VITE_ROUTER_BASENAME', '/')),
    embedded,
    storageNs: envString('VITE_STORAGE_NS', 'agents'),
    cookiePath: envString('VITE_COOKIE_PATH', '/'),
    apiBaseUrl: normApiBaseUrl(envString('VITE_API_BASE_URL', '')),
    apiTimeoutMs: envInt('VITE_API_TIMEOUT', 15000),
    errorDedupWindowMs: envInt('VITE_ERROR_DEDUP_WINDOW_MS', 3000),
    eventWindowLimit: envInt('VITE_EVENT_WINDOW_LIMIT', 1000),
    eventPageSize: envInt('VITE_EVENT_PAGE_SIZE', 50),
    sseBufferMax: envInt('VITE_SSE_BUFFER_MAX', 300),
    sseFlushIntervalMs: envInt('VITE_SSE_FLUSH_INTERVAL_MS', 500),
    sseRetryMax: envInt('VITE_SSE_RETRY_MAX', 5),
    sseRetryBaseMs: envInt('VITE_SSE_RETRY_BASE_MS', 1000),
    sseRetryMaxMs: envInt('VITE_SSE_RETRY_MAX_MS', 16000),
  };
  return _instance;
}

/** 获取配置单例（未初始化时自动初始化，避免模块加载时序问题） */
export function getConfig(): AppRuntimeConfig {
  return _instance ?? initConfig();
}
