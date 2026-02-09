import type { JobStatus } from '@/api/types.ts';
import { getSemanticTokens } from '@/theme/tokens.ts';

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
export const getStepStatus = (s: JobStatus) => STATUS_STEP_MAP[s] ?? 'wait';

/** 状态 → 语义色映射（运行时根据主题解析 hex 值） */
export function getStatusSemanticColor(s: JobStatus, isDark: boolean): string {
  const tokens = getSemanticTokens(isDark);
  const map: Partial<Record<JobStatus, string>> = {
    running: tokens.statusRunning,
    queued: tokens.statusRunning,
    verifying: tokens.statusRunning,
    packaging: tokens.statusRunning,
    succeeded: tokens.statusSucceeded,
    failed: tokens.statusFailed,
    aborted: tokens.statusAborted,
    waiting_approval: tokens.statusWarning,
  };
  return map[s] ?? tokens.textSecondary;
}
