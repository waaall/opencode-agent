/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BASE_PATH?: string;
  readonly VITE_ROUTER_BASENAME?: string;
  readonly VITE_EMBEDDED?: string;
  readonly VITE_STORAGE_NS?: string;
  readonly VITE_COOKIE_PATH?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_API_TIMEOUT?: string;
  readonly VITE_ERROR_DEDUP_WINDOW_MS?: string;
  readonly VITE_EVENT_WINDOW_LIMIT?: string;
  readonly VITE_EVENT_PAGE_SIZE?: string;
  readonly VITE_SSE_BUFFER_MAX?: string;
  readonly VITE_SSE_FLUSH_INTERVAL_MS?: string;
  readonly VITE_SSE_RETRY_MAX?: string;
  readonly VITE_SSE_RETRY_BASE_MS?: string;
  readonly VITE_SSE_RETRY_MAX_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
