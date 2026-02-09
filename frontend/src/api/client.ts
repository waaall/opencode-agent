import axios, { AxiosHeaders } from 'axios';
import { message } from 'antd';
import { getConfig } from '@/config/app-config.ts';

const cfg = getConfig();

const apiClient = axios.create({
  timeout: cfg.apiTimeoutMs,
});

// 错误去重窗口，避免轮询错误风暴
const recentErrorMap = new Map<string, number>();

function generateRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function detectClientPlatform(): 'web' | 'desktop' {
  if (typeof window === 'undefined') return 'web';
  const globalWindow = window as unknown as Record<string, unknown>;
  return globalWindow.__TAURI__ || globalWindow.__TAURI_INTERNALS__ ? 'desktop' : 'web';
}

function readAuthToken(): string | null {
  if (typeof window === 'undefined') return null;

  try {
    const scopedKey = `${cfg.storageNs}:auth:token`;
    const candidates = [
      localStorage.getItem(scopedKey),
      sessionStorage.getItem(scopedKey),
      localStorage.getItem('auth_token'),
      sessionStorage.getItem('auth_token'),
    ];
    return candidates.find((v): v is string => Boolean(v)) ?? null;
  } catch {
    return null;
  }
}

function extractErrorMessage(error: unknown): string {
  if (!error || typeof error !== 'object') return '请求失败';
  const e = error as { response?: { data?: unknown }; message?: string };
  const data = e.response?.data as Record<string, unknown> | undefined;
  if (typeof data?.message === 'string') return data.message;
  if (typeof data?.detail === 'string') return data.detail;
  if (typeof data?.error === 'string') return data.error;
  return e.message ?? '请求失败';
}

function extractErrorCode(error: unknown): string | null {
  if (!error || typeof error !== 'object') return null;
  const e = error as { response?: { data?: unknown } };
  const data = e.response?.data as Record<string, unknown> | undefined;
  return typeof data?.code === 'string' ? data.code : null;
}

apiClient.interceptors.request.use((config) => {
  const headers = AxiosHeaders.from(config.headers);

  if (!headers.has('X-Request-Id')) {
    headers.set('X-Request-Id', generateRequestId());
  }
  if (!headers.has('X-Client-Platform')) {
    headers.set('X-Client-Platform', detectClientPlatform());
  }
  if (!headers.has('Authorization')) {
    const token = readAuthToken();
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }

  config.headers = headers;
  return config;
});

// 响应拦截器：统一错误提示（支持静默 + 去重）
apiClient.interceptors.response.use((res) => res, (error) => {
  const msg = extractErrorMessage(error);
  const code = extractErrorCode(error);
  const status = error.response?.status ?? '网络错误';
  const headers = AxiosHeaders.from(error.config?.headers);
  const silent = headers.get('x-silent-error') === '1';
  const dedupKey = `${status}:${code ?? '-'}:${msg}`;
  const now = Date.now();
  const lastTs = recentErrorMap.get(dedupKey) ?? 0;

  if (!silent && now - lastTs > cfg.errorDedupWindowMs) {
    message.error(`${status}${code ? ` [${code}]` : ''}: ${msg}`);
    recentErrorMap.set(dedupKey, now);
  }
  return Promise.reject(error);
});

export default apiClient;
