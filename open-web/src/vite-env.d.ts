/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_API_PROXY_TARGET: string;
  readonly VITE_APP_DOWNLOAD_URL: string;
  readonly VITE_DEFAULT_LOCALE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
