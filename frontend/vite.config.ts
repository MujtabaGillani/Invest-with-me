import { fileURLToPath } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/**
 * Vite configuration.
 *
 * The dev server proxies `/api` to the backend rather than having the frontend
 * call `http://localhost:8000` directly. That keeps requests same-origin in
 * development, so cookie-based authentication (when it arrives) and CORS behave
 * the same locally as they will behind a reverse proxy in production.
 */
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // Fail loudly instead of silently moving to 5174, which would leave the
    // backend's CORS allow-list pointing at the wrong origin.
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    // Source maps in production: this is an internal tool, and being able to read
    // a real stack trace from a bug report is worth more than hiding the bundle.
    sourcemap: true,
  },
});
