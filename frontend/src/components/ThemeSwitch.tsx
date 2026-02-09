import { Segmented } from 'antd';
import { useThemeStore, type ThemeMode } from '@/theme/theme-store.ts';

const OPTIONS = [
  { value: 'light', label: '浅色' },
  { value: 'system', label: '系统' },
  { value: 'dark', label: '深色' },
];

// 主题切换控件（Segmented 选择器）
export default function ThemeSwitch() {
  const themeMode = useThemeStore((s) => s.themeMode);
  const setThemeMode = useThemeStore((s) => s.setThemeMode);

  return (
    <Segmented
      size="small"
      options={OPTIONS}
      value={themeMode}
      onChange={(val) => setThemeMode(val as ThemeMode)}
    />
  );
}
