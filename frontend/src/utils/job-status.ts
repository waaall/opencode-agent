import type { JobStatus } from '@/api/types.ts';

// 状态 → 显示标签映射
const STATUS_LABEL_MAP: Record<JobStatus, string> = {
  created: '已创建',
  queued: '排队中',
  running: '执行中',
  waiting_approval: '等待审批',
  verifying: '验证中',
  packaging: '打包中',
  succeeded: '已完成',
  failed: '失败',
  aborted: '已中止',
};

// 状态 → Antd Tag 颜色映射
const STATUS_COLOR_MAP: Record<JobStatus, string> = {
  created: 'default',
  queued: 'processing',
  running: 'processing',
  waiting_approval: 'warning',
  verifying: 'processing',
  packaging: 'processing',
  succeeded: 'success',
  failed: 'error',
  aborted: 'default',
};

// 状态 → Steps 组件 status 映射
const STATUS_STEP_MAP: Record<JobStatus, 'wait' | 'process' | 'finish' | 'error'> = {
  created: 'process',
  queued: 'process',
  running: 'process',
  waiting_approval: 'process',
  verifying: 'process',
  packaging: 'process',
  succeeded: 'finish',
  failed: 'error',
  aborted: 'error',
};

export const getStatusLabel = (s: JobStatus): string => STATUS_LABEL_MAP[s] ?? s;
export const getStatusColor = (s: JobStatus): string => STATUS_COLOR_MAP[s] ?? 'default';
export const getStepStatus = (s: JobStatus) => STATUS_STEP_MAP[s] ?? 'wait';
