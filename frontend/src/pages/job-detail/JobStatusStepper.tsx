import { Steps } from 'antd';
import type { JobStatus } from '@/api/types.ts';
import { JOB_STATUS_STEPS } from '@/constants/job-states.ts';
import { useThemeStore } from '@/theme/theme-store.ts';
import { getStatusLabel, getStepStatus, getStatusSemanticColor } from '@/utils/job-status.ts';

interface Props {
  status: JobStatus;
}

// 状态机步骤条：根据当前状态高亮对应步骤
export default function JobStatusStepper({ status }: Props) {
  const resolvedDark = useThemeStore((s) => s.resolvedDark);
  const currentIndex = JOB_STATUS_STEPS.indexOf(status);
  const isFailed = status === 'failed';
  const isAborted = status === 'aborted';
  const isTerminalError = isFailed || isAborted;

  // 终态为 succeeded 时所有步骤完成；失败/中止时在最后一个活跃步骤标红
  const stepStatus = isTerminalError ? 'error' : getStepStatus(status);

  const items = JOB_STATUS_STEPS.map((s) => ({
    title: (
      <span style={{ color: getStatusSemanticColor(s, resolvedDark) }}>
        {getStatusLabel(s)}
      </span>
    ),
  }));

  // 失败/中止追加一个错误步骤
  if (isTerminalError) {
    items.push({
      title: (
        <span style={{ color: getStatusSemanticColor(status, resolvedDark) }}>
          {getStatusLabel(status)}
        </span>
      ),
    });
  }

  return (
    <Steps
      current={isTerminalError ? items.length - 1 : Math.max(currentIndex, 0)}
      status={stepStatus}
      items={items}
      size="small"
      style={{ marginBottom: 24 }}
    />
  );
}
