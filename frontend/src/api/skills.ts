import apiClient from './client.ts';
import type { SkillResponse } from './types.ts';

export const listSkills = (taskType?: string) =>
  apiClient.get<SkillResponse[]>('/skills', { params: taskType ? { task_type: taskType } : {} })
    .then((r) => r.data);

export const getSkill = (code: string) =>
  apiClient.get<SkillResponse>(`/skills/${code}`).then((r) => r.data);
