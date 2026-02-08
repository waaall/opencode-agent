import { Menu } from 'antd';
import {
  DashboardOutlined,
  PlusCircleOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '工作台' },
  { key: '/jobs/new', icon: <PlusCircleOutlined />, label: '新建任务' },
  { key: '/jobs', icon: <HistoryOutlined />, label: '任务历史' },
];

export default function Sider() {
  const navigate = useNavigate();
  const location = useLocation();

  // 匹配当前路径到菜单 key
  const selectedKey = location.pathname === '/'
    ? '/'
    : menuItems.find((item) => item.key !== '/' && location.pathname.startsWith(item.key))?.key ?? '/';

  return (
    <Menu
      mode="inline"
      selectedKeys={[selectedKey]}
      items={menuItems}
      onClick={({ key }) => navigate(key)}
      style={{ height: '100%', borderRight: 0 }}
    />
  );
}
