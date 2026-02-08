import { create } from 'zustand';
import type { SkillResponse } from '@/api/types.ts';
import { listSkills } from '@/api/skills.ts';

interface SkillStore {
  skills: SkillResponse[];
  loading: boolean;
  fetch: () => Promise<void>;
}

export const useSkillStore = create<SkillStore>((set, get) => ({
  skills: [],
  loading: false,
  fetch: async () => {
    if (get().skills.length > 0) return; // 已缓存则跳过
    set({ loading: true });
    try {
      const skills = await listSkills();
      set({ skills, loading: false });
    } catch {
      set({ loading: false });
    }
  },
}));
