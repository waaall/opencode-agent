import axios from 'axios';
import { message } from 'antd';
import { getConfig } from '@/config/app-config.ts';

const cfg = getConfig();

const apiClient = axios.create({
  baseURL: cfg.apiBase,
  timeout: cfg.apiTimeoutMs,
});

// 错误去重窗口，避免轮询错误风暴
const recentErrorMap = new Map<string, number>();

// 响应拦截器：统一错误提示（支持静默 + 去重）
apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    const msg = error.response?.data?.detail ?? '请求失败';
    const status = error.response?.status ?? '网络错误';
    const silent = error.config?.headers?.['x-silent-error'] === '1';
    const dedupKey = `${status}:${msg}`;
    const now = Date.now();
    const lastTs = recentErrorMap.get(dedupKey) ?? 0;

    if (!silent && now - lastTs > cfg.errorDedupWindowMs) {
      message.error(`${status}: ${msg}`);
      recentErrorMap.set(dedupKey, now);
    }
    return Promise.reject(error);
  },
);

export default apiClient;
