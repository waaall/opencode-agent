// 任务状态枚举，与后端 JobStatus 一一对应
export type JobStatus =
  | 'created' | 'queued' | 'running' | 'waiting_approval'
  | 'verifying' | 'packaging' | 'succeeded' | 'failed' | 'aborted';

export interface JobCreateRequest {
  requirement: string;
  files: File[];
  skill_code?: string;
  agent?: string;
  model_provider_id?: string;
  model_id?: string;
  output_contract?: Record<string, unknown>;
  idempotency_key?: string;
}

export interface JobCreateResponse {
  job_id: string;
  status: string;
  selected_skill: string;
}

export interface JobStartResponse {
  job_id: string;
  status: string;
}

export interface JobDetailResponse {
  job_id: string;
  status: JobStatus;
  session_id: string | null;
  selected_skill: string;
  agent: string;
  model: { providerID: string; modelID: string } | null;
  error_code: string | null;
  error_message: string | null;
  download_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobEvent {
  job_id: string;
  status: string | null;
  source: 'api' | 'worker' | 'opencode';
  event_type: string;
  message: string | null;
  payload: Record<string, unknown> | null;
  created_at: string | null;
}

export interface ArtifactItem {
  id: number;
  category: 'output' | 'bundle';
  relative_path: string;
  mime_type: string | null;
  size_bytes: number;
  sha256: string;
  created_at: string;
}

export interface ArtifactListResponse {
  job_id: string;
  artifacts: ArtifactItem[];
  bundle_ready: boolean;
}

export interface SkillResponse {
  code: string;
  name: string;
  aliases: string[];
  version: string;
  schema_version: string;
  description: string;
  task_type: string;
  sample_output_contract: Record<string, unknown> | null;
}

// 任务列表响应（后端需补充此端点）
export interface JobListResponse {
  items: JobDetailResponse[];
  total: number;
  page: number;
  page_size: number;
}
