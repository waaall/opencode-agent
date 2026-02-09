import { Layout } from 'antd';
import { Outlet } from 'react-router-dom';
import BusinessHeader from './BusinessHeader.tsx';

const { Content } = Layout;

// Portal 模式最小壳层：仅 BusinessHeader + Content
export default function PortalShell() {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <BusinessHeader />
      <Content style={{ padding: 24 }}>
        <Outlet />
      </Content>
    </Layout>
  );
}
