import { Typography } from 'antd';
import JobCreateForm from './JobCreateForm.tsx';

export default function JobCreate() {
  return (
    <div>
      <Typography.Title level={3}>新建任务</Typography.Title>
      <JobCreateForm />
    </div>
  );
}
