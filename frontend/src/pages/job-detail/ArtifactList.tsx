import { Table, Button, Space } from 'antd';
import { DownloadOutlined, EyeOutlined } from '@ant-design/icons';
import type { ArtifactItem } from '@/api/types.ts';
import { artifactDownloadUrl } from '@/api/jobs.ts';
import { formatFileSize } from '@/utils/format.ts';
import { getFileName } from '@/utils/file-type.ts';

interface Props {
  jobId: string;
  artifacts: ArtifactItem[];
  onPreview: (artifact: ArtifactItem) => void;
}

export default function ArtifactList({ jobId, artifacts, onPreview }: Props) {
  const columns = [
    {
      title: '文件名',
      dataIndex: 'relative_path',
      key: 'name',
      render: (path: string) => getFileName(path),
    },
    {
      title: '类型',
      dataIndex: 'category',
      key: 'category',
      width: 100,
    },
    {
      title: 'MIME',
      dataIndex: 'mime_type',
      key: 'mime',
      width: 160,
      render: (v: string | null) => v ?? '-',
    },
    {
      title: '大小',
      dataIndex: 'size_bytes',
      key: 'size',
      width: 100,
      render: (v: number) => formatFileSize(v),
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: unknown, record: ArtifactItem) => (
        <Space>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => onPreview(record)}
          >
            预览
          </Button>
          <Button
            size="small"
            icon={<DownloadOutlined />}
            href={artifactDownloadUrl(jobId, record.id)}
          >
            下载
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Table
      dataSource={artifacts}
      columns={columns}
      rowKey="id"
      size="small"
      pagination={false}
    />
  );
}
