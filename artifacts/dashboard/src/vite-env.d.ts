/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_WORKER_API_KEY: string;
  readonly VITE_ADMIN_KEY: string;
  readonly VITE_TOTP_SECRET: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
