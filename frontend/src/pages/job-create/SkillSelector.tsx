import { useEffect } from 'react';
import { Select, Form } from 'antd';
import { useSkillStore } from '@/stores/skill.ts';

// 技能选择器：可选字段，不选则由后端自动路由
export default function SkillSelector() {
  const skills = useSkillStore((s) => s.skills);
  const loading = useSkillStore((s) => s.loading);
  const fetch = useSkillStore((s) => s.fetch);

  useEffect(() => { fetch(); }, [fetch]);

  return (
    <Form.Item
      name="skill_code"
      label="技能"
      tooltip="不选则由后端自动路由到最匹配的技能"
    >
      <Select
        allowClear
        showSearch
        placeholder="自动选择"
        loading={loading}
        optionFilterProp="label"
        options={skills.map((s) => ({
          value: s.code,
          label: `${s.name} (${s.code})`,
          title: s.description,
        }))}
      />
    </Form.Item>
  );
}
