import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Spin } from 'antd';
import AppLayout from '@/layouts/AppLayout.tsx';

// 懒加载页面，拆分 chunk（bundle-dynamic-imports）
const Dashboard = lazy(() => import('@/pages/dashboard/index.tsx'));
const JobCreate = lazy(() => import('@/pages/job-create/index.tsx'));
const JobDetail = lazy(() => import('@/pages/job-detail/index.tsx'));
const JobList = lazy(() => import('@/pages/job-list/index.tsx'));

// 页面加载 fallback
const PageFallback = (
  <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
    <Spin size="large" />
  </div>
);

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Suspense fallback={PageFallback}><Dashboard /></Suspense>} />
          <Route path="jobs" element={<Suspense fallback={PageFallback}><JobList /></Suspense>} />
          <Route path="jobs/new" element={<Suspense fallback={PageFallback}><JobCreate /></Suspense>} />
          <Route path="jobs/:jobId" element={<Suspense fallback={PageFallback}><JobDetail /></Suspense>} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
