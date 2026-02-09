import { useMemo } from 'react';
import { useThemeStore } from './theme-store.ts';
import { getSemanticTokens, type SemanticTokens } from './tokens.ts';

/** 便捷 hook：返回当前主题的语义 token */
export function useSemanticTokens(): SemanticTokens {
  const resolvedDark = useThemeStore((s) => s.resolvedDark);
  return useMemo(() => getSemanticTokens(resolvedDark), [resolvedDark]);
}
