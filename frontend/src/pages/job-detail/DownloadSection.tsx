import { Button, Space } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { bundleDownloadUrl } from '@/api/jobs.ts';

interface Props {
  jobId: string;
  bundleReady: boolean;
}

// 打包下载按钮
export default function DownloadSection({ jobId, bundleReady }: Props) {
  return (
    <Space>
      <Button
        type="primary"
        icon={<DownloadOutlined />}
        href={bundleDownloadUrl(jobId)}
        disabled={!bundleReady}
      >
        下载打包产物
      </Button>
    </Space>
  );
}
