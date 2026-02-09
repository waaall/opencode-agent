import apiClient from './client.ts';
import type { SkillResponse } from './types.ts';
import { API } from '@/constants/api.ts';
import { buildApiUrl } from './url.ts';

export const listSkills = (taskType?: string) =>
  apiClient.get<SkillResponse[]>(buildApiUrl(API.SKILLS), { params: taskType ? { task_type: taskType } : {} })
    .then((r) => r.data);

export const getSkill = (code: string) =>
  apiClient.get<SkillResponse>(buildApiUrl(API.SKILL(code))).then((r) => r.data);
