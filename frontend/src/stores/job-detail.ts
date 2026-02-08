import { create } from 'zustand';
import type { JobDetailResponse, JobEvent } from '@/api/types.ts';

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

const EVENT_WINDOW_LIMIT = 1000;
const EVENT_PAGE_SIZE = 50;

export const useJobDetailStore = create<JobDetailStore>((set) => ({
  job: null,
  events: [],
  eventPage: 1,
  pageSize: EVENT_PAGE_SIZE,
  sseStatus: 'idle',

  setJob: (job) => set({ job }),
  // 追加事件并裁剪到窗口上限
  appendEvents: (batch) => set((s) => {
    const merged = [...s.events, ...batch];
    const nextEvents = merged.length > EVENT_WINDOW_LIMIT
      ? merged.slice(merged.length - EVENT_WINDOW_LIMIT)
      : merged;
    return { events: nextEvents };
  }),
  setEventPage: (eventPage) => set({ eventPage }),
  setSseStatus: (sseStatus) => set({ sseStatus }),
  reset: () => set({ job: null, events: [], eventPage: 1, pageSize: EVENT_PAGE_SIZE, sseStatus: 'idle' }),
}));
