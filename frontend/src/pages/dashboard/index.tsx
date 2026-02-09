import { Typography, Button, Card } from 'antd';
import { PlusCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useSemanticTokens } from '@/theme/useSemanticTokens.ts';
import SkillCards from './SkillCards.tsx';
import RecentJobs from './RecentJobs.tsx';

export default function Dashboard() {
  const navigate = useNavigate();
  const tokens = useSemanticTokens();

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: tokens.spacingLg }}>
        <Typography.Title level={3} style={{ margin: 0 }}>工作台</Typography.Title>
        <Button
          type="primary"
          icon={<PlusCircleOutlined />}
          onClick={() => navigate('/jobs/new')}
        >
          新建任务
        </Button>
      </div>

      {/* 技能卡片区 */}
      <Card
        title="可用技能"
        style={{ marginBottom: tokens.spacingLg, boxShadow: tokens.shadowLight }}
        styles={{ body: { padding: tokens.spacingLg } }}
      >
        <SkillCards />
      </Card>

      {/* 最近任务区 */}
      <Card
        title="最近任务"
        style={{ boxShadow: tokens.shadowLight }}
        styles={{ body: { padding: tokens.spacingLg } }}
      >
        <RecentJobs />
      </Card>
    </div>
  );
}
