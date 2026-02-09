// 语义 token 体系：统一管理明暗主题下的所有视觉变量

export interface SemanticTokens {
  // 背景
  bgPage: string;
  bgCard: string;
  bgCardHover: string;
  bgSider: string;
  bgHeader: string;
  // 文字
  textPrimary: string;
  textSecondary: string;
  textDisabled: string;
  // 边框
  borderDefault: string;
  borderLight: string;
  // 状态色（语义化，页面不直写 hex）
  statusRunning: string;
  statusSucceeded: string;
  statusFailed: string;
  statusAborted: string;
  statusWarning: string;
  // 品牌色
  colorPrimary: string;
  colorPrimaryHover: string;
  // 阴影
  shadowLight: string;
  shadowMedium: string;
  shadowHeavy: string;
  // 圆角
  radiusSm: number;
  radiusMd: number;
  radiusLg: number;
  radiusXl: number;
  // 间距
  spacingXs: number;
  spacingSm: number;
  spacingMd: number;
  spacingLg: number;
  spacingXl: number;
  spacingXxl: number;
  // 动效
  motionFast: string;
  motionNormal: string;
  motionSlow: string;
  motionEasing: string;
}

export const lightTokens: SemanticTokens = {
  bgPage: '#f0f2f5',
  bgCard: '#ffffff',
  bgCardHover: '#fafafa',
  bgSider: '#ffffff',
  bgHeader: 'rgba(255, 255, 255, 0.85)',
  textPrimary: 'rgba(0, 0, 0, 0.88)',
  textSecondary: 'rgba(0, 0, 0, 0.65)',
  textDisabled: 'rgba(0, 0, 0, 0.25)',
  borderDefault: '#d9d9d9',
  borderLight: '#f0f0f0',
  statusRunning: '#1677ff',
  statusSucceeded: '#52c41a',
  statusFailed: '#ff4d4f',
  statusAborted: '#8c8c8c',
  statusWarning: '#faad14',
  colorPrimary: '#0d9488',
  colorPrimaryHover: '#14b8a6',
  shadowLight: '0 1px 2px rgba(0, 0, 0, 0.04)',
  shadowMedium: '0 2px 8px rgba(0, 0, 0, 0.08)',
  shadowHeavy: '0 6px 16px rgba(0, 0, 0, 0.12)',
  radiusSm: 4,
  radiusMd: 8,
  radiusLg: 12,
  radiusXl: 16,
  spacingXs: 4,
  spacingSm: 8,
  spacingMd: 12,
  spacingLg: 16,
  spacingXl: 24,
  spacingXxl: 32,
  motionFast: '120ms',
  motionNormal: '180ms',
  motionSlow: '240ms',
  motionEasing: 'cubic-bezier(0.4, 0, 0.2, 1)',
};

export const darkTokens: SemanticTokens = {
  bgPage: '#141414',
  bgCard: '#1f1f1f',
  bgCardHover: '#2a2a2a',
  bgSider: '#1f1f1f',
  bgHeader: 'rgba(31, 31, 31, 0.9)',
  textPrimary: 'rgba(255, 255, 255, 0.88)',
  textSecondary: 'rgba(255, 255, 255, 0.65)',
  textDisabled: 'rgba(255, 255, 255, 0.25)',
  borderDefault: '#424242',
  borderLight: '#303030',
  statusRunning: '#1668dc',
  statusSucceeded: '#49aa19',
  statusFailed: '#d32029',
  statusAborted: '#6c6c6c',
  statusWarning: '#d89614',
  colorPrimary: '#14b8a6',
  colorPrimaryHover: '#2dd4bf',
  shadowLight: '0 1px 2px rgba(0, 0, 0, 0.2)',
  shadowMedium: '0 2px 8px rgba(0, 0, 0, 0.3)',
  shadowHeavy: '0 6px 16px rgba(0, 0, 0, 0.4)',
  radiusSm: 4,
  radiusMd: 8,
  radiusLg: 12,
  radiusXl: 16,
  spacingXs: 4,
  spacingSm: 8,
  spacingMd: 12,
  spacingLg: 16,
  spacingXl: 24,
  spacingXxl: 32,
  motionFast: '120ms',
  motionNormal: '180ms',
  motionSlow: '240ms',
  motionEasing: 'cubic-bezier(0.4, 0, 0.2, 1)',
};

/** 根据 resolved dark 状态获取对应主题 tokens */
export function getSemanticTokens(isDark: boolean): SemanticTokens {
  return isDark ? darkTokens : lightTokens;
}
