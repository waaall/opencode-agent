import { create } from 'zustand';
import type { JobDetailResponse, JobEvent } from '@/api/types.ts';
import { getConfig } from '@/config/app-config.ts';

interface JobDetailStore {
  job: JobDetailResponse | null;
  events: JobEvent[];
  eventPage: number;
  pageSize: number;
  sseStatus: 'idle' | 'connected' | 'error';

  setJob: (job: JobDetailResponse) => void;
  appendEvents: (batch: JobEvent[]) => void;
  setEventPage: (page: number) => void;
  setSseStatus: (s: 'idle' | 'connected' | 'error') => void;
  reset: () => void;
}

// 从配置中心读取事件窗口和分页参数
const cfg = getConfig();

export const useJobDetailStore = create<JobDetailStore>((set) => ({
  job: null,
  events: [],
  eventPage: 1,
  pageSize: cfg.eventPageSize,
  sseStatus: 'idle',

  setJob: (job) => set({ job }),
  // 追加事件并裁剪到窗口上限
  appendEvents: (batch) => set((s) => {
    const merged = [...s.events, ...batch];
    const nextEvents = merged.length > cfg.eventWindowLimit
      ? merged.slice(merged.length - cfg.eventWindowLimit)
      : merged;
    return { events: nextEvents };
  }),
  setEventPage: (eventPage) => set({ eventPage }),
  setSseStatus: (sseStatus) => set({ sseStatus }),
  reset: () => set({ job: null, events: [], eventPage: 1, pageSize: cfg.eventPageSize, sseStatus: 'idle' }),
}));
