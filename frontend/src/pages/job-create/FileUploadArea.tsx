import { Upload, Form } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd';

const { Dragger } = Upload;

// 文件上传拖拽区域，至少上传 1 个文件
export default function FileUploadArea() {
  return (
    <Form.Item
      name="files"
      label="上传文件"
      valuePropName="fileList"
      getValueFromEvent={normFile}
      rules={[
        { required: true, message: '至少上传 1 个文件' },
        {
          validator: (_, value: UploadFile[] | undefined) =>
            value && value.length > 0
              ? Promise.resolve()
              : Promise.reject(new Error('至少上传 1 个文件')),
        },
      ]}
    >
      <Dragger
        multiple
        beforeUpload={() => false}
        accept="*"
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
        <p className="ant-upload-hint">支持多文件上传</p>
      </Dragger>
    </Form.Item>
  );
}

// 从 Upload 事件中提取 fileList
function normFile(e: { fileList: UploadFile[] } | UploadFile[]) {
  if (Array.isArray(e)) return e;
  return e?.fileList;
}
