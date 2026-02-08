import { useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import {
  Typography, Descriptions, Badge, Button, Popconfirm, Alert, Card, Divider, Space,
} from 'antd';
import { useJobDetailStore } from '@/stores/job-detail.ts';
import { useJobEvents } from '@/hooks/use-job-events.ts';
import { usePolling } from '@/hooks/use-polling.ts';
import { getJob, abortJob } from '@/api/jobs.ts';
import { isActiveStatus, TERMINAL_STATUSES } from '@/constants/job-states.ts';
import { getStatusLabel, getStatusColor } from '@/utils/job-status.ts';
import { formatDateTime } from '@/utils/format.ts';
import JobStatusStepper from './JobStatusStepper.tsx';
import JobEventLog from './JobEventLog.tsx';
import ArtifactSection from './ArtifactSection.tsx';

// SSE 连接状态 Badge 颜色映射
const SSE_BADGE: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  connected: 'success',
  error: 'warning',
  idle: 'default',
};

export default function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const job = useJobDetailStore((s) => s.job);
  const sseStatus = useJobDetailStore((s) => s.sseStatus);
  const setJob = useJobDetailStore((s) => s.setJob);
  const reset = useJobDetailStore((s) => s.reset);

  const isActive = job ? isActiveStatus(job.status) : false;
  const isTerminal = job ? TERMINAL_STATUSES.has(job.status) : false;

  // 进入页面时重置 store
  useEffect(() => {
    reset();
    return () => reset();
  }, [jobId, reset]);

  // SSE 事件流连接
  useJobEvents(jobId ?? null, isActive);

  // 轮询任务状态，终态自动停止
  const pollCallback = useCallback(async (): Promise<boolean> => {
    if (!jobId) return true;
    const data = await getJob(jobId, { silentError: true });
    setJob(data);
    return TERMINAL_STATUSES.has(data.status);
  }, [jobId, setJob]);

  usePolling(pollCallback, 3000, !!jobId);

  // 中止任务
  const handleAbort = useCallback(async () => {
    if (!jobId) return;
    const data = await abortJob(jobId);
    setJob(data);
  }, [jobId, setJob]);

  if (!jobId) return null;

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          任务详情
        </Typography.Title>
        <Badge status={SSE_BADGE[sseStatus] ?? 'default'} text={`SSE: ${sseStatus}`} />
      </Space>

      {/* 状态步骤条 */}
      {job ? <JobStatusStepper status={job.status} /> : null}

      {/* 错误信息 */}
      {job?.status === 'failed' && job.error_message ? (
        <Alert
          type="error"
          showIcon
          message={`错误 [${job.error_code ?? 'UNKNOWN'}]`}
          description={job.error_message}
          style={{ marginBottom: 16 }}
        />
      ) : null}

      {/* 基本信息 */}
      {job ? (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Descriptions column={2} size="small">
            <Descriptions.Item label="任务 ID">{job.job_id}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Badge color={getStatusColor(job.status)} text={getStatusLabel(job.status)} />
            </Descriptions.Item>
            <Descriptions.Item label="技能">{job.selected_skill}</Descriptions.Item>
            <Descriptions.Item label="Agent">{job.agent}</Descriptions.Item>
            <Descriptions.Item label="模型">
              {job.model ? `${job.model.providerID} / ${job.model.modelID}` : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">{formatDateTime(job.created_at)}</Descriptions.Item>
          </Descriptions>
        </Card>
      ) : null}

      {/* 中止按钮 */}
      {isActive ? (
        <div style={{ marginBottom: 16 }}>
          <Popconfirm
            title="确定要中止此任务吗？"
            onConfirm={handleAbort}
            okText="确定"
            cancelText="取消"
          >
            <Button danger>中止任务</Button>
          </Popconfirm>
        </div>
      ) : null}

      {/* 产物区域（终态时显示） */}
      {isTerminal ? (
        <>
          <Divider>产物</Divider>
          <ArtifactSection jobId={jobId} />
        </>
      ) : null}

      {/* 事件日志 */}
      <Divider>事件日志</Divider>
      <JobEventLog />
    </div>
  );
}
