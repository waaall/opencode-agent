import { Table, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useJobListStore } from '@/stores/job-list.ts';
import type { JobDetailResponse, JobStatus } from '@/api/types.ts';
import { getStatusLabel, getStatusColor } from '@/utils/job-status.ts';
import { formatDateTime } from '@/utils/format.ts';

// 任务历史表格 + 分页
export default function JobTable() {
  const items = useJobListStore((s) => s.items);
  const total = useJobListStore((s) => s.total);
  const page = useJobListStore((s) => s.page);
  const pageSize = useJobListStore((s) => s.pageSize);
  const loading = useJobListStore((s) => s.loading);
  const setPage = useJobListStore((s) => s.setPage);
  const fetch = useJobListStore((s) => s.fetch);
  const navigate = useNavigate();

  const columns = [
    {
      title: '任务 ID',
      dataIndex: 'job_id',
      key: 'job_id',
      ellipsis: true,
    },
    {
      title: '技能',
      dataIndex: 'selected_skill',
      key: 'skill',
      width: 140,
    },
    {
      title: 'Agent',
      dataIndex: 'agent',
      key: 'agent',
      width: 120,
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
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
  ];

  return (
    <Table
      dataSource={items}
      columns={columns}
      rowKey="job_id"
      loading={loading}
      pagination={{
        current: page,
        pageSize,
        total,
        showSizeChanger: false,
        onChange: (p) => {
          setPage(p);
          // 翻页后自动拉取新数据
          setTimeout(fetch, 0);
        },
      }}
      onRow={(record: JobDetailResponse) => ({
        onClick: () => navigate(`/jobs/${record.job_id}`),
        style: { cursor: 'pointer' },
      })}
    />
  );
}
