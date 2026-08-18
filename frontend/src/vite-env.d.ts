/// <reference types="vite/client" />

/**
 * Typed environment variables.
 *
 * Without this, `import.meta.env.VITE_API_BASE_URL` is `any`, and the type-aware
 * lint rules correctly flag assigning it anywhere. Declaring the shape here means
 * a typo in a variable name is a compile error rather than an `undefined` that
 * silently falls through to a default at runtime.
 */
interface ImportMetaEnv {
  /** Base URL the app calls. Defaults to the Vite dev proxy path. */
  readonly VITE_API_BASE_URL?: string;
  /** Dev-only: where the Vite proxy forwards `/api`. Not read by app code. */
  readonly VITE_PROXY_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
