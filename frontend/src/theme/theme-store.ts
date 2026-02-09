import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { getConfig } from '@/config/app-config.ts';

export type ThemeMode = 'system' | 'light' | 'dark';

interface ThemeStore {
  themeMode: ThemeMode;
  resolvedDark: boolean;
  setThemeMode: (mode: ThemeMode) => void;
  syncSystemPreference: (isDark: boolean) => void;
}

/** 根据用户设置和系统偏好计算最终是否深色 */
function resolveIsDark(mode: ThemeMode, systemDark: boolean): boolean {
  if (mode === 'dark') return true;
  if (mode === 'light') return false;
  return systemDark;
}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set, get) => ({
      themeMode: 'system' as ThemeMode,
      resolvedDark: false,

      setThemeMode: (themeMode) => {
        const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        set({ themeMode, resolvedDark: resolveIsDark(themeMode, systemDark) });
      },

      // 系统主题变化时同步（仅 system 模式下生效）
      syncSystemPreference: (isDark) => {
        const { themeMode } = get();
        if (themeMode === 'system') {
          set({ resolvedDark: isDark });
        }
      },
    }),
    {
      name: `${getConfig().storageNs}:theme`,
      storage: createJSONStorage(() => localStorage),
      // 仅持久化用户选择，resolvedDark 动态计算
      partialize: (state) => ({ themeMode: state.themeMode }),
      // 恢复后根据持久化的 themeMode 重算 resolvedDark
      merge: (persisted, current) => {
        const saved = persisted as Partial<ThemeStore> | undefined;
        const themeMode = saved?.themeMode ?? current.themeMode;
        const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        return {
          ...current,
          themeMode,
          resolvedDark: resolveIsDark(themeMode, systemDark),
        };
      },
    },
  ),
);
