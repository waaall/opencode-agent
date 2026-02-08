import { useEffect, useState, useCallback } from 'react';
import { Spin, Empty } from 'antd';
import type { ArtifactItem, ArtifactListResponse } from '@/api/types.ts';
import { getArtifacts } from '@/api/jobs.ts';
import ArtifactList from './ArtifactList.tsx';
import ArtifactPreview from './ArtifactPreview.tsx';
import DownloadSection from './DownloadSection.tsx';

interface Props {
  jobId: string;
}

// 产物区域容器：加载产物列表 + 预览 + 下载
export default function ArtifactSection({ jobId }: Props) {
  const [data, setData] = useState<ArtifactListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [previewItem, setPreviewItem] = useState<ArtifactItem | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getArtifacts(jobId)
      .then((res) => { if (!cancelled) setData(res); })
      .catch(() => { /* 错误由拦截器处理 */ })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [jobId]);

  const handleClosePreview = useCallback(() => setPreviewItem(null), []);

  if (loading) return <Spin />;
  if (!data || data.artifacts.length === 0) {
    return <Empty description="暂无产物" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <div>
      <DownloadSection jobId={jobId} bundleReady={data.bundle_ready} />
      <div style={{ marginTop: 16 }}>
        <ArtifactList
          jobId={jobId}
          artifacts={data.artifacts}
          onPreview={setPreviewItem}
        />
      </div>
      <ArtifactPreview
        jobId={jobId}
        artifact={previewItem}
        onClose={handleClosePreview}
      />
    </div>
  );
}
