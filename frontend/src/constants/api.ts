// API 端点路径常量
export const API = {
  JOBS: '/jobs',
  JOB: (id: string) => `/jobs/${id}`,
  JOB_START: (id: string) => `/jobs/${id}/start`,
  JOB_ABORT: (id: string) => `/jobs/${id}/abort`,
  JOB_EVENTS: (id: string) => `/jobs/${id}/events`,
  JOB_ARTIFACTS: (id: string) => `/jobs/${id}/artifacts`,
  JOB_DOWNLOAD: (id: string) => `/jobs/${id}/download`,
  ARTIFACT_DOWNLOAD: (jobId: string, artifactId: number) =>
    `/jobs/${jobId}/artifacts/${artifactId}/download`,
  SKILLS: '/skills',
  SKILL: (code: string) => `/skills/${code}`,
} as const;
