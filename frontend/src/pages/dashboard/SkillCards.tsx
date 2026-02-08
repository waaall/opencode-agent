import { useEffect } from 'react';
import { Card, Row, Col, Spin, Empty, Typography } from 'antd';
import { useSkillStore } from '@/stores/skill.ts';

// 技能卡片网格
export default function SkillCards() {
  const skills = useSkillStore((s) => s.skills);
  const loading = useSkillStore((s) => s.loading);
  const fetch = useSkillStore((s) => s.fetch);

  useEffect(() => { fetch(); }, [fetch]);

  if (loading) return <Spin />;
  if (skills.length === 0) return <Empty description="暂无技能" image={Empty.PRESENTED_IMAGE_SIMPLE} />;

  return (
    <Row gutter={[16, 16]}>
      {skills.map((skill) => (
        <Col xs={24} sm={12} md={8} lg={6} key={skill.code}>
          <Card
            size="small"
            title={skill.name}
            extra={<Typography.Text type="secondary">{skill.version}</Typography.Text>}
          >
            <Typography.Paragraph
              ellipsis={{ rows: 2, expandable: false }}
              style={{ marginBottom: 4 }}
            >
              {skill.description}
            </Typography.Paragraph>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {skill.task_type} · {skill.code}
            </Typography.Text>
          </Card>
        </Col>
      ))}
    </Row>
  );
}
