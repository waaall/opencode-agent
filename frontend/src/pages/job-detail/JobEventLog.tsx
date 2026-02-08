import { Timeline, Pagination, Tag, Typography, Empty } from 'antd';
import { useJobDetailStore } from '@/stores/job-detail.ts';
import { formatDateTime } from '@/utils/format.ts';

const SOURCE_COLOR: Record<string, string> = {
  api: 'blue',
  worker: 'green',
  opencode: 'purple',
};

// 事件日志列表：最近 N 条窗口内前端分页
export default function JobEventLog() {
  const events = useJobDetailStore((s) => s.events);
  const page = useJobDetailStore((s) => s.eventPage);
  const pageSize = useJobDetailStore((s) => s.pageSize);
  const setEventPage = useJobDetailStore((s) => s.setEventPage);

  const total = events.length;
  if (total === 0) {
    return <Empty description="暂无事件" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  // 倒序分页：第 1 页显示最新事件
  const start = Math.max(total - page * pageSize, 0);
  const end = total - (page - 1) * pageSize;
  const visibleEvents = events.slice(start, end).reverse();

  return (
    <div>
      <Timeline
        items={visibleEvents.map((evt, i) => ({
          key: i,
          children: (
            <div>
              <div style={{ marginBottom: 4 }}>
                <Tag color={SOURCE_COLOR[evt.source] ?? 'default'}>{evt.source}</Tag>
                <Typography.Text strong>{evt.event_type}</Typography.Text>
                <Typography.Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                  {formatDateTime(evt.created_at)}
                </Typography.Text>
              </div>
              {evt.message ? (
                <Typography.Text>{evt.message}</Typography.Text>
              ) : null}
            </div>
          ),
        }))}
      />
      {total > pageSize ? (
        <Pagination
          current={page}
          pageSize={pageSize}
          total={total}
          onChange={setEventPage}
          size="small"
          showSizeChanger={false}
          style={{ textAlign: 'center' }}
        />
      ) : null}
    </div>
  );
}
