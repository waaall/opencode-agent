import { create } from 'zustand';

interface SettingsStore {
  drawerOpen: boolean;
  openDrawer: () => void;
  closeDrawer: () => void;
}

// 设置抽屉状态管理
export const useSettingsStore = create<SettingsStore>()((set) => ({
  drawerOpen: false,
  openDrawer: () => set({ drawerOpen: true }),
  closeDrawer: () => set({ drawerOpen: false }),
}));
