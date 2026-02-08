import { Tabs } from 'antd';
import { useJobListStore } from '@/stores/job-list.ts';

const STATUS_TABS = [
  { key: 'all', label: '全部' },
  { key: 'running', label: '运行中' },
  { key: 'succeeded', label: '已完成' },
  { key: 'failed', label: '失败' },
];

// 状态筛选 Tabs
export default function StatusFilter() {
  const statusFilter = useJobListStore((s) => s.statusFilter);
  const setStatusFilter = useJobListStore((s) => s.setStatusFilter);

  return (
    <Tabs
      activeKey={statusFilter ?? 'all'}
      onChange={(key) => setStatusFilter(key === 'all' ? undefined : key)}
      items={STATUS_TABS}
      style={{ marginBottom: 0 }}
    />
  );
}
