// MIME → 预览策略映射
export type PreviewStrategy = 'markdown' | 'image' | 'text' | 'pdf' | 'none';

export function getPreviewStrategy(mime: string | null): PreviewStrategy {
  if (!mime) return 'none';
  if (mime === 'text/markdown') return 'markdown';
  if (mime.startsWith('image/')) return 'image';
  if (mime === 'application/pdf') return 'pdf';
  if (mime.startsWith('text/')) return 'text';
  return 'none';
}

// 从文件路径提取文件名
export function getFileName(path: string): string {
  return path.split('/').pop() ?? path;
}
