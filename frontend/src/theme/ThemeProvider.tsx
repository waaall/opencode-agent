import { useEffect, useMemo } from 'react';
import { ConfigProvider, theme as antdTheme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useThemeStore } from './theme-store.ts';
import { getSemanticTokens } from './tokens.ts';

// 主题 Provider：matchMedia 监听 + html data-theme + Ant Design 算法切换
export default function ThemeProvider({ children }: { children: React.ReactNode }) {
  const resolvedDark = useThemeStore((s) => s.resolvedDark);
  const syncSystemPreference = useThemeStore((s) => s.syncSystemPreference);

  // 监听系统主题变化（client-event-listeners: 注册 + 清理）
  useEffect(() => {
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => syncSystemPreference(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [syncSystemPreference]);

  // 同步 html data-theme 属性，供非 Ant Design 样式使用
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolvedDark ? 'dark' : 'light');
  }, [resolvedDark]);

  // Ant Design 主题配置（rerender-dependencies: 仅 resolvedDark 变化时重算）
  const themeConfig = useMemo(() => {
    const tokens = getSemanticTokens(resolvedDark);
    return {
      algorithm: resolvedDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
      token: {
        colorPrimary: tokens.colorPrimary,
        borderRadius: tokens.radiusMd,
        colorBgLayout: tokens.bgPage,
      },
    };
  }, [resolvedDark]);

  return (
    <ConfigProvider locale={zhCN} theme={themeConfig}>
      {children}
    </ConfigProvider>
  );
}
