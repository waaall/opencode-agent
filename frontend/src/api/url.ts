import { getConfig } from '@/config/app-config.ts';

/** 统一组装 apiBaseUrl + endpoint，endpoint 必须是 / 开头的绝对路径片段 */
export function joinUrl(apiBaseUrl: string, endpoint: string): string {
  if (!endpoint.startsWith('/')) {
    throw new Error(`endpoint must start with "/": ${endpoint}`);
  }
  if (!apiBaseUrl) return endpoint;

  const base = apiBaseUrl.replace(/\/+$/, '');
  return `${base}${endpoint}`;
}

export function buildApiUrl(endpoint: string): string {
  return joinUrl(getConfig().apiBaseUrl, endpoint);
}
