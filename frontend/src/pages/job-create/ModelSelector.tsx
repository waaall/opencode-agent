import { Form, Select, Space } from 'antd';

// 模型供应商和模型选项（可后续改为从后端获取）
const MODEL_PROVIDERS = [
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'openai', label: 'OpenAI' },
];

const MODEL_OPTIONS: Record<string, { value: string; label: string }[]> = {
  anthropic: [
    { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4' },
    { value: 'claude-opus-4-20250514', label: 'Claude Opus 4' },
  ],
  openai: [
    { value: 'gpt-4o', label: 'GPT-4o' },
    { value: 'o3', label: 'o3' },
  ],
};

// 模型选择器：供应商 + 模型两个级联 Select
export default function ModelSelector() {
  const form = Form.useFormInstance();
  const providerId = Form.useWatch('model_provider_id', form);

  return (
    <Space.Compact style={{ width: '100%' }}>
      <Form.Item
        name="model_provider_id"
        label="模型供应商"
        style={{ width: '50%', marginBottom: 0 }}
      >
        <Select
          allowClear
          placeholder="可选"
          options={MODEL_PROVIDERS}
          onChange={() => form.setFieldValue('model_id', undefined)}
        />
      </Form.Item>
      <Form.Item
        name="model_id"
        label="模型"
        style={{ width: '50%', marginBottom: 0 }}
      >
        <Select
          allowClear
          placeholder="可选"
          disabled={!providerId}
          options={providerId ? MODEL_OPTIONS[providerId] ?? [] : []}
        />
      </Form.Item>
    </Space.Compact>
  );
}
