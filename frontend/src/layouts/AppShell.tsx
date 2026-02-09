import { lazy, Suspense } from 'react';
import { getConfig } from '@/config/app-config.ts';

const StandaloneShell = lazy(() => import('./StandaloneShell.tsx'));
const PortalShell = lazy(() => import('./PortalShell.tsx'));

const ShellFallback = <div style={{ minHeight: '100vh' }} />;

// 根据配置选择 Shell（bundle-conditional: 条件渲染不同布局）
export default function AppShell() {
  const { mode } = getConfig();
  if (mode === 'portal') {
    return (
      <Suspense fallback={ShellFallback}>
        <PortalShell />
      </Suspense>
    );
  }
  return (
    <Suspense fallback={ShellFallback}>
      <StandaloneShell />
    </Suspense>
  );
}
