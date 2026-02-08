import { Typography, Button, Divider } from 'antd';
import { PlusCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import SkillCards from './SkillCards.tsx';
import RecentJobs from './RecentJobs.tsx';

export default function Dashboard() {
  const navigate = useNavigate();

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography.Title level={3} style={{ margin: 0 }}>工作台</Typography.Title>
        <Button
          type="primary"
          icon={<PlusCircleOutlined />}
          onClick={() => navigate('/jobs/new')}
        >
          新建任务
        </Button>
      </div>

      <Divider>可用技能</Divider>
      <SkillCards />

      <Divider>最近任务</Divider>
      <RecentJobs />
    </div>
  );
}
