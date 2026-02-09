import { startTransition, useEffect, useRef } from 'react';
import { useJobDetailStore } from '@/stores/job-detail.ts';
import { getConfig } from '@/config/app-config.ts';
import type { JobEvent } from '@/api/types.ts';
import { API } from '@/constants/api.ts';
import { buildApiUrl } from '@/api/url.ts';

// SSE 连接管理：ref 缓冲高频数据，定时批量写入 store
// 所有参数从配置中心读取，不硬编码
export function useJobEvents(jobId: string | null, enabled: boolean) {
  const appendEvents = useJobDetailStore((s) => s.appendEvents);
  const setSseStatus = useJobDetailStore((s) => s.setSseStatus);
  const bufferRef = useRef<JobEvent[]>([]);
  const retryRef = useRef(0);

  useEffect(() => {
    if (!jobId || !enabled) return;

    const cfg = getConfig();
    let es: EventSource | null = null;
    let disposed = false;
    let flushTimer: ReturnType<typeof setInterval> | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const pushEvent = (event: JobEvent) => {
      bufferRef.current.push(event);
      // 防止缓冲区过大
      if (bufferRef.current.length > cfg.sseBufferMax) {
        bufferRef.current = bufferRef.current.slice(bufferRef.current.length - cfg.sseBufferMax);
      }
    };

    const flush = () => {
      if (bufferRef.current.length === 0) return;
      const batch = [...bufferRef.current];
      bufferRef.current = [];
      // 使用 startTransition 降低优先级，避免阻塞用户交互（rerender-transitions）
      startTransition(() => {
        appendEvents(batch);
      });
    };

    const connect = () => {
      if (disposed) return;
      es = new EventSource(buildApiUrl(API.JOB_EVENTS(jobId)));

      es.onopen = () => {
        setSseStatus('connected');
        retryRef.current = 0;
      };

      // onmessage 兜底接收所有事件
      es.onmessage = (e) => {
        try {
          pushEvent(JSON.parse(e.data));
        } catch { /* keep-alive / 非 JSON 忽略 */ }
      };

      // 已知事件类型通过 addEventListener 接收
      const knownTypes = [
        'skill.router.fallback', 'job.enqueued', 'opencode.prompt_async.sent',
        'session.updated', 'session.retry', 'permission.replied', 'job.failed',
      ];
      for (const type of knownTypes) {
        es.addEventListener(type, (e: MessageEvent) => {
          try { pushEvent(JSON.parse(e.data)); } catch { /* skip */ }
        });
      }

      es.onerror = () => {
        setSseStatus('error');
        es?.close();
        // 指数退避重连
        if (retryRef.current < cfg.sseRetryMax) {
          const delay = Math.min(cfg.sseRetryBaseMs * 2 ** retryRef.current, cfg.sseRetryMaxMs);
          retryRef.current += 1;
          retryTimer = setTimeout(connect, delay);
        }
      };
    };

    connect();
    // 定时批量刷新到 store
    flushTimer = setInterval(flush, cfg.sseFlushIntervalMs);

    return () => {
      disposed = true;
      es?.close();
      if (flushTimer) clearInterval(flushTimer);
      if (retryTimer) clearTimeout(retryTimer);
      flush(); // 清理时刷出剩余事件
    };
  }, [jobId, enabled, appendEvents, setSseStatus]);
}
