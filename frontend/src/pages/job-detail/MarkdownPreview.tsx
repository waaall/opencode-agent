import { useEffect, useState } from 'react';
import { Spin, Alert } from 'antd';

interface Props {
  url: string;
}

// 懒加载 Markdown 预览：先 fetch 内容，再渲染
export default function MarkdownPreview({ url }: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.text();
      })
      .then((text) => { if (!cancelled) setContent(text); })
      .catch((e) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [url]);

  if (error) return <Alert type="error" message="加载失败" description={error} />;
  if (content === null) return <Spin />;

  return (
    <pre style={{
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-word',
      maxHeight: 500,
      overflow: 'auto',
      padding: 16,
      background: '#f5f5f5',
      borderRadius: 4,
    }}>
      {content}
    </pre>
  );
}
