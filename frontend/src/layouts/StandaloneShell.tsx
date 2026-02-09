import { Layout, theme } from 'antd';
import { Outlet } from 'react-router-dom';
import SiderNav from './Sider.tsx';
import SettingsButton from '@/components/SettingsButton.tsx';
import SettingsDrawer from '@/components/SettingsDrawer.tsx';

const { Header, Sider, Content } = Layout;

// Standalone 模式完整壳层：全局 Header + Sider + Content
export default function StandaloneShell() {
  const { token } = theme.useToken();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: token.colorBgContainer,
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
          padding: '0 24px',
        }}
      >
        <h1 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>OpenCode Orchestrator</h1>
        <SettingsButton />
      </Header>
      <Layout>
        <Sider width={200} style={{ background: token.colorBgContainer }}>
          <SiderNav />
        </Sider>
        <Content style={{ padding: 24, minHeight: 280 }}>
          <Outlet />
        </Content>
      </Layout>
      <SettingsDrawer />
    </Layout>
  );
}
