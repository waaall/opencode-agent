import { useCallback, useState } from 'react';
import { Form, Input, Button, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import type { UploadFile } from 'antd';
import { createJob, startJob } from '@/api/jobs.ts';
import { getConfig } from '@/config/app-config.ts';
import SkillSelector from './SkillSelector.tsx';
import FileUploadArea from './FileUploadArea.tsx';
import ModelSelector from './ModelSelector.tsx';

// localStorage key 使用命名空间前缀（client-localstorage-schema）
const IDEMPOTENCY_STORAGE_KEY = `${getConfig().storageNs}:v1:job-create:idempotency-key`;

// 生成幂等键
function generateIdempotencyKey(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

// 获取或创建幂等键
function getOrCreateIdempotencyKey(): string {
  let key = localStorage.getItem(IDEMPOTENCY_STORAGE_KEY);
  if (!key) {
    key = generateIdempotencyKey();
    localStorage.setItem(IDEMPOTENCY_STORAGE_KEY, key);
  }
  return key;
}

function clearIdempotencyKey() {
  localStorage.removeItem(IDEMPOTENCY_STORAGE_KEY);
}

interface FormValues {
  requirement: string;
  files: UploadFile[];
  skill_code?: string;
  model_provider_id?: string;
  model_id?: string;
}

export default function JobCreateForm() {
  const [form] = Form.useForm<FormValues>();
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = useCallback(async (values: FormValues) => {
    setSubmitting(true);
    try {
      const files = values.files
        .map((f) => f.originFileObj)
        .filter((f): f is NonNullable<typeof f> => f !== undefined) as File[];

      if (files.length === 0) {
        message.error('至少上传 1 个文件');
        return;
      }

      const idempotencyKey = getOrCreateIdempotencyKey();

      // 创建任务 → 启动任务 → 跳转详情页（async-parallel：两步串行，因有依赖）
      const { job_id } = await createJob({
        requirement: values.requirement,
        files,
        skill_code: values.skill_code,
        model_provider_id: values.model_provider_id,
        model_id: values.model_id,
        idempotency_key: idempotencyKey,
      });

      await startJob(job_id);
      clearIdempotencyKey();
      message.success('任务已创建并启动');
      navigate(`/jobs/${job_id}`);
    } catch {
      message.error('创建任务失败，请重试');
    } finally {
      setSubmitting(false);
    }
  }, [navigate]);

  const handleReset = useCallback(() => {
    form.resetFields();
    clearIdempotencyKey();
  }, [form]);

  return (
    <Form
      form={form}
      layout="vertical"
      onFinish={handleSubmit}
      style={{ maxWidth: 720 }}
    >
      <Form.Item
        name="requirement"
        label="需求描述"
        rules={[{ required: true, message: '请输入需求描述' }]}
      >
        <Input.TextArea
          rows={6}
          placeholder="描述你的需求，越详细越好..."
        />
      </Form.Item>

      <FileUploadArea />
      <SkillSelector />

      <Form.Item label="模型配置（可选）">
        <ModelSelector />
      </Form.Item>

      <Form.Item>
        <Button
          type="primary"
          htmlType="submit"
          loading={submitting}
          style={{ marginRight: 12 }}
        >
          创建并启动
        </Button>
        <Button onClick={handleReset}>
          重置表单
        </Button>
      </Form.Item>
    </Form>
  );
}
