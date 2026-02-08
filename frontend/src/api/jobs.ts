import apiClient from './client.ts';
import type {
  JobCreateRequest,
  JobCreateResponse,
  JobStartResponse,
  JobDetailResponse,
  JobListResponse,
  ArtifactListResponse,
} from './types.ts';

// 创建任务：multipart/form-data
export async function createJob(data: JobCreateRequest): Promise<JobCreateResponse> {
  if (data.files.length === 0) {
    throw new Error('至少上传 1 个文件');
  }

  const form = new FormData();
  form.append('requirement', data.requirement);
  data.files.forEach((f) => form.append('files', f));
  if (data.skill_code) form.append('skill_code', data.skill_code);
  if (data.agent) form.append('agent', data.agent);
  if (data.model_provider_id && data.model_id) {
    form.append('model_provider_id', data.model_provider_id);
    form.append('model_id', data.model_id);
  }
  if (data.output_contract) form.append('output_contract', JSON.stringify(data.output_contract));
  if (data.idempotency_key) form.append('idempotency_key', data.idempotency_key);

  const res = await apiClient.post<JobCreateResponse>('/jobs', form);
  return res.data;
}

export const startJob = (jobId: string) =>
  apiClient.post<JobStartResponse>(`/jobs/${jobId}/start`).then((r) => r.data);

export const getJob = (jobId: string, opts?: { silentError?: boolean }) =>
  apiClient.get<JobDetailResponse>(`/jobs/${jobId}`, {
    headers: opts?.silentError ? { 'x-silent-error': '1' } : undefined,
  }).then((r) => r.data);

export const listJobs = (params: { page?: number; page_size?: number; status?: string }) =>
  apiClient.get<JobListResponse>('/jobs', { params }).then((r) => r.data);

export const abortJob = (jobId: string) =>
  apiClient.post<JobDetailResponse>(`/jobs/${jobId}/abort`).then((r) => r.data);

export const getArtifacts = (jobId: string) =>
  apiClient.get<ArtifactListResponse>(`/jobs/${jobId}/artifacts`).then((r) => r.data);

// 下载链接直接拼 URL，浏览器原生下载
export const bundleDownloadUrl = (jobId: string) =>
  `${import.meta.env.VITE_API_BASE}/jobs/${jobId}/download`;

export const artifactDownloadUrl = (jobId: string, artifactId: number) =>
  `${import.meta.env.VITE_API_BASE}/jobs/${jobId}/artifacts/${artifactId}/download`;
