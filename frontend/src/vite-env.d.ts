/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Gốc URL của API khi web và API khác origin (Static Site riêng). Trống = cùng origin. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
