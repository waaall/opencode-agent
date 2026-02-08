import { lazy, Suspense } from 'react';
import { Modal, Spin, Image, Typography } from 'antd';
import { FileOutlined } from '@ant-design/icons';
import type { ArtifactItem } from '@/api/types.ts';
import { artifactDownloadUrl } from '@/api/jobs.ts';
import { getPreviewStrategy, getFileName } from '@/utils/file-type.ts';
import { formatFileSize } from '@/utils/format.ts';

// 懒加载 Markdown 渲染器（bundle-dynamic-imports）
const MarkdownPreview = lazy(() => import('./MarkdownPreview.tsx'));

interface Props {
  jobId: string;
  artifact: ArtifactItem | null;
  onClose: () => void;
}

// 按 MIME 类型懒加载不同预览渲染器
export default function ArtifactPreview({ jobId, artifact, onClose }: Props) {
  if (!artifact) return null;

  const url = artifactDownloadUrl(jobId, artifact.id);
  const strategy = getPreviewStrategy(artifact.mime_type);
  const fileName = getFileName(artifact.relative_path);

  return (
    <Modal
      open={!!artifact}
      title={fileName}
      onCancel={onClose}
      footer={null}
      width={800}
      destroyOnClose
    >
      {strategy === 'image' ? (
        <Image src={url} alt={fileName} style={{ maxWidth: '100%' }} />
      ) : strategy === 'markdown' ? (
        <Suspense fallback={<Spin />}>
          <MarkdownPreview url={url} />
        </Suspense>
      ) : strategy === 'text' ? (
        <Suspense fallback={<Spin />}>
          <MarkdownPreview url={url} />
        </Suspense>
      ) : (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <FileOutlined style={{ fontSize: 48, color: '#999' }} />
          <Typography.Paragraph style={{ marginTop: 16 }}>
            {fileName} ({formatFileSize(artifact.size_bytes)})
          </Typography.Paragraph>
          <Typography.Text type="secondary">
            此文件类型不支持在线预览，请下载查看
          </Typography.Text>
        </div>
      )}
    </Modal>
  );
}
