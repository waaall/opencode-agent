import { Button, Tooltip } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { useSettingsStore } from '@/stores/settings-store.ts';
import { useSemanticTokens } from '@/theme/useSemanticTokens.ts';

// 设置按钮：Header 右侧齿轮图标
export default function SettingsButton() {
  const openDrawer = useSettingsStore((s) => s.openDrawer);
  const tokens = useSemanticTokens();

  return (
    <Tooltip title="设置" placement="bottom">
      <Button
        type="text"
        icon={
          <SettingOutlined
            style={{
              fontSize: 18,
              color: tokens.textSecondary,
              transition: `transform ${tokens.motionNormal} ${tokens.motionEasing}`,
            }}
          />
        }
        onClick={openDrawer}
        style={{
          width: 36,
          height: 36,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderRadius: tokens.radiusMd,
        }}
      />
    </Tooltip>
  );
}
