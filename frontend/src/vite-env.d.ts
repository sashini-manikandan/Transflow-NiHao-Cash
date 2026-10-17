/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Which seeded demo user the frontend identifies as. Not a credential. */
  readonly VITE_DEMO_USER?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
