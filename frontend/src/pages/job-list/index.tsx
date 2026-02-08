import { useEffect } from 'react';
import { Typography } from 'antd';
import { useJobListStore } from '@/stores/job-list.ts';
import StatusFilter from './StatusFilter.tsx';
import JobTable from './JobTable.tsx';

export default function JobList() {
  const fetch = useJobListStore((s) => s.fetch);

  // 进入页面时加载数据
  useEffect(() => { fetch(); }, [fetch]);

  return (
    <div>
      <Typography.Title level={3}>任务历史</Typography.Title>
      <StatusFilter />
      <JobTable />
    </div>
  );
}
