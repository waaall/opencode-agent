import { create } from 'zustand';
import type { JobDetailResponse } from '@/api/types.ts';
import { listJobs } from '@/api/jobs.ts';

interface JobListStore {
  items: JobDetailResponse[];
  total: number;
  page: number;
  pageSize: number;
  statusFilter: string | undefined;
  loading: boolean;

  setPage: (page: number) => void;
  setStatusFilter: (status: string | undefined) => void;
  fetch: () => Promise<void>;
}

export const useJobListStore = create<JobListStore>((set, get) => ({
  items: [],
  total: 0,
  page: 1,
  pageSize: 20,
  statusFilter: undefined,
  loading: false,

  setPage: (page) => set({ page }),
  setStatusFilter: (statusFilter) => set({ statusFilter, page: 1 }),

  fetch: async () => {
    const { page, pageSize, statusFilter } = get();
    set({ loading: true });
    try {
      const res = await listJobs({ page, page_size: pageSize, status: statusFilter });
      set({ items: res.items, total: res.total, loading: false });
    } catch {
      set({ loading: false });
    }
  },
}));
