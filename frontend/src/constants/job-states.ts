import type { JobStatus } from '@/api/types.ts';

// 状态机步骤顺序（用于 Steps 组件）
export const JOB_STATUS_STEPS: JobStatus[] = [
  'created', 'queued', 'running', 'waiting_approval',
  'verifying', 'packaging', 'succeeded',
];

// 终态集合
export const TERMINAL_STATUSES: ReadonlySet<JobStatus> = new Set([
  'succeeded', 'failed', 'aborted',
]);

// 是否为活跃状态（需要轮询/SSE）
export const isActiveStatus = (s: JobStatus): boolean => !TERMINAL_STATUSES.has(s);
