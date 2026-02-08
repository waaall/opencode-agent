import axios from 'axios';
import { message } from 'antd';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE,
  timeout: 15_000,
});

// 错误去重窗口，避免轮询错误风暴
const recentErrorMap = new Map<string, number>();
const ERROR_DEDUP_WINDOW_MS = 3000;

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

    if (!silent && now - lastTs > ERROR_DEDUP_WINDOW_MS) {
      message.error(`${status}: ${msg}`);
      recentErrorMap.set(dedupKey, now);
    }
    return Promise.reject(error);
  },
);

export default apiClient;
