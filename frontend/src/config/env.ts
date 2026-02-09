// 环境变量解析工具

/** 读取字符串环境变量，缺失时返回默认值 */
export function envString(key: string, fallback: string): string {
  return import.meta.env[key] ?? fallback;
}

/** 读取整数环境变量，解析失败时返回默认值并打印警告（仅开发环境） */
export function envInt(key: string, fallback: number): number {
  const raw = import.meta.env[key];
  if (raw === undefined || raw === '') return fallback;
  const n = parseInt(raw, 10);
  if (Number.isNaN(n)) {
    if (import.meta.env.DEV) {
      console.warn(`[config] env ${key}="${raw}" 解析失败，回退默认值 ${fallback}`);
    }
    return fallback;
  }
  return n;
}

/** 读取布尔环境变量 */
export function envBool(key: string, fallback: boolean): boolean {
  const raw = import.meta.env[key];
  if (raw === undefined || raw === '') return fallback;
  return raw === 'true' || raw === '1';
}

/** basePath 规范化：确保以 / 开头且以 / 结尾 */
export function normBasePath(raw: string): string {
  let p = raw.startsWith('/') ? raw : `/${raw}`;
  if (!p.endsWith('/')) p += '/';
  return p;
}

/** routerBasename 规范化：以 / 开头，根路径除外不以 / 结尾 */
export function normRouterBasename(raw: string): string {
  let p = raw.startsWith('/') ? raw : `/${raw}`;
  if (p.length > 1 && p.endsWith('/')) p = p.slice(0, -1);
  return p;
}
