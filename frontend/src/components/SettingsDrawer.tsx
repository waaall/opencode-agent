import { useMemo, useCallback } from 'react';
import { Drawer, Tooltip, theme } from 'antd';
import {
  SunOutlined,
  MoonOutlined,
  LaptopOutlined,
  CheckOutlined,
} from '@ant-design/icons';
import { useSettingsStore } from '@/stores/settings-store.ts';
import { useThemeStore, type ThemeMode } from '@/theme/theme-store.ts';
import { useSemanticTokens } from '@/theme/useSemanticTokens.ts';

// 主题选项配置
const THEME_OPTIONS: { value: ThemeMode; label: string; icon: React.ReactNode }[] = [
  { value: 'light', label: '浅色模式', icon: <SunOutlined /> },
  { value: 'system', label: '跟随系统', icon: <LaptopOutlined /> },
  { value: 'dark', label: '深色模式', icon: <MoonOutlined /> },
];

// 设置区块标题组件
function SectionTitle({ children }: { children: React.ReactNode }) {
  const tokens = useSemanticTokens();
  return (
    <div
      style={{
        fontSize: 11,
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        color: tokens.textSecondary,
        marginBottom: 12,
        paddingBottom: 8,
        borderBottom: `1px solid ${tokens.borderLight}`,
      }}
    >
      {children}
    </div>
  );
}

// 主题选择卡片
function ThemeCard({
  option,
  isActive,
  onClick,
}: {
  option: (typeof THEME_OPTIONS)[number];
  isActive: boolean;
  onClick: () => void;
}) {
  const tokens = useSemanticTokens();
  const { token } = theme.useToken();

  return (
    <Tooltip title={option.label} placement="bottom">
      <button
        type="button"
        onClick={onClick}
        style={{
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          flex: 1,
          padding: '16px 8px',
          border: `1.5px solid ${isActive ? tokens.colorPrimary : tokens.borderDefault}`,
          borderRadius: tokens.radiusLg,
          background: isActive
            ? `${tokens.colorPrimary}10`
            : tokens.bgCard,
          cursor: 'pointer',
          transition: `all ${tokens.motionNormal} ${tokens.motionEasing}`,
          outline: 'none',
        }}
        onMouseEnter={(e) => {
          if (!isActive) {
            e.currentTarget.style.borderColor = tokens.colorPrimaryHover;
            e.currentTarget.style.background = tokens.bgCardHover;
          }
        }}
        onMouseLeave={(e) => {
          if (!isActive) {
            e.currentTarget.style.borderColor = tokens.borderDefault;
            e.currentTarget.style.background = tokens.bgCard;
          }
        }}
      >
        {/* 选中指示器 */}
        {isActive && (
          <span
            style={{
              position: 'absolute',
              top: 6,
              right: 6,
              width: 16,
              height: 16,
              borderRadius: '50%',
              background: tokens.colorPrimary,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <CheckOutlined style={{ fontSize: 9, color: '#fff' }} />
          </span>
        )}
        <span
          style={{
            fontSize: 22,
            color: isActive ? tokens.colorPrimary : token.colorTextSecondary,
            transition: `color ${tokens.motionNormal} ${tokens.motionEasing}`,
          }}
        >
          {option.icon}
        </span>
        <span
          style={{
            fontSize: 12,
            fontWeight: isActive ? 600 : 400,
            color: isActive ? tokens.colorPrimary : tokens.textSecondary,
            transition: `color ${tokens.motionNormal} ${tokens.motionEasing}`,
          }}
        >
          {option.label}
        </span>
      </button>
    </Tooltip>
  );
}

// 设置抽屉主组件
export default function SettingsDrawer() {
  const drawerOpen = useSettingsStore((s) => s.drawerOpen);
  const closeDrawer = useSettingsStore((s) => s.closeDrawer);
  const themeMode = useThemeStore((s) => s.themeMode);
  const setThemeMode = useThemeStore((s) => s.setThemeMode);
  const tokens = useSemanticTokens();

  // 稳定回调避免子组件不必要的重渲染
  const handleThemeChange = useCallback(
    (mode: ThemeMode) => setThemeMode(mode),
    [setThemeMode],
  );

  // 构建主题卡片列表
  const themeCards = useMemo(
    () =>
      THEME_OPTIONS.map((opt) => (
        <ThemeCard
          key={opt.value}
          option={opt}
          isActive={themeMode === opt.value}
          onClick={() => handleThemeChange(opt.value)}
        />
      )),
    [themeMode, handleThemeChange],
  );

  return (
    <Drawer
      title={
        <span style={{ fontWeight: 600, fontSize: 16, letterSpacing: '-0.01em' }}>
          设置
        </span>
      }
      placement="right"
      width={340}
      onClose={closeDrawer}
      open={drawerOpen}
      styles={{
        body: {
          padding: '20px 24px',
          display: 'flex',
          flexDirection: 'column',
          gap: 28,
        },
        header: {
          borderBottom: `1px solid ${tokens.borderLight}`,
        },
      }}
    >
      {/* 外观设置 */}
      <section>
        <SectionTitle>外观</SectionTitle>
        <div style={{ display: 'flex', gap: 10 }}>
          {themeCards}
        </div>
      </section>

      {/* 预留：更多设置区域 */}
      <section>
        <SectionTitle>通用</SectionTitle>
        <div
          style={{
            padding: '20px 16px',
            borderRadius: tokens.radiusMd,
            border: `1px dashed ${tokens.borderDefault}`,
            textAlign: 'center',
            color: tokens.textDisabled,
            fontSize: 13,
          }}
        >
          更多设置即将推出
        </div>
      </section>
    </Drawer>
  );
}
