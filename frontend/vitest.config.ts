import { defineConfig, mergeConfig } from 'vitest/config';

import viteConfig from './vite.config';

/**
 * Test configuration, kept separate from the build configuration.
 *
 * Vite's own `defineConfig` does not accept a `test` key, and merging here means
 * the tests resolve imports through exactly the same alias and plugin setup the
 * application builds with - so a passing test cannot be relying on a different
 * module graph from production.
 */
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      // Component tests assert on structure and text, never on styling, so
      // processing CSS would be pure cost.
      css: false,
      coverage: {
        provider: 'v8',
        include: ['src/**/*.{ts,tsx}'],
        exclude: [
          'src/**/*.test.{ts,tsx}',
          'src/test/**',
          // Generated from the backend's schema; nothing to cover.
          'src/types/**',
          'src/main.tsx',
        ],
      },
    },
  }),
);
