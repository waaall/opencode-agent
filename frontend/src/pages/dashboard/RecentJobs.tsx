import { useEffect } from 'react';
import { Table, Tag, Empty } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useJobListStore } from '@/stores/job-list.ts';
import type { JobDetailResponse, JobStatus } from '@/api/types.ts';
import { getStatusLabel, getStatusColor } from '@/utils/job-status.ts';
import { formatRelativeTime } from '@/utils/format.ts';

// 最近任务表格（首页展示最近 10 条）
export default function RecentJobs() {
  const items = useJobListStore((s) => s.items);
  const loading = useJobListStore((s) => s.loading);
  const fetch = useJobListStore((s) => s.fetch);
  const navigate = useNavigate();

  useEffect(() => { fetch(); }, [fetch]);

  const columns = [
    {
      title: '任务 ID',
      dataIndex: 'job_id',
      key: 'job_id',
      ellipsis: true,
      width: 280,
    },
    {
      title: '技能',
      dataIndex: 'selected_skill',
      key: 'skill',
      width: 140,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: JobStatus) => (
        <Tag color={getStatusColor(status)}>{getStatusLabel(status)}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 140,
      render: (v: string) => formatRelativeTime(v),
    },
  ];

  if (!loading && items.length === 0) {
    return <Empty description="暂无任务" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <Table
      dataSource={items.slice(0, 10)}
      columns={columns}
      rowKey="job_id"
      size="small"
      loading={loading}
      pagination={false}
      onRow={(record: JobDetailResponse) => ({
        onClick: () => navigate(`/jobs/${record.job_id}`),
        style: { cursor: 'pointer' },
      })}
    />
  );
}
