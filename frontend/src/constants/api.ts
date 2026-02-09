// API 端点路径常量
const API_PREFIX = '/api/v1';

export const API = {
  JOBS: `${API_PREFIX}/jobs`,
  JOB: (id: string) => `${API_PREFIX}/jobs/${id}`,
  JOB_START: (id: string) => `${API_PREFIX}/jobs/${id}/start`,
  JOB_ABORT: (id: string) => `${API_PREFIX}/jobs/${id}/abort`,
  JOB_EVENTS: (id: string) => `${API_PREFIX}/jobs/${id}/events`,
  JOB_ARTIFACTS: (id: string) => `${API_PREFIX}/jobs/${id}/artifacts`,
  JOB_DOWNLOAD: (id: string) => `${API_PREFIX}/jobs/${id}/download`,
  ARTIFACT_DOWNLOAD: (jobId: string, artifactId: number) =>
    `${API_PREFIX}/jobs/${jobId}/artifacts/${artifactId}/download`,
  SKILLS: `${API_PREFIX}/skills`,
  SKILL: (code: string) => `${API_PREFIX}/skills/${code}`,
} as const;
