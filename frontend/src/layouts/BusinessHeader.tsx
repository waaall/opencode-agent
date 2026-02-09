import { theme, Typography } from 'antd';
import SettingsButton from '@/components/SettingsButton.tsx';
import SettingsDrawer from '@/components/SettingsDrawer.tsx';

// Portal 模式下的精简顶栏（无全局导航）
export default function BusinessHeader() {
  const { token } = theme.useToken();

  return (
    <>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 24px',
          height: 56,
          background: token.colorBgContainer,
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        <Typography.Text strong style={{ fontSize: 16 }}>
          OpenCode Orchestrator
        </Typography.Text>
        <SettingsButton />
      </div>
      <SettingsDrawer />
    </>
  );
}
