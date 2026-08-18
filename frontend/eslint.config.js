import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

/**
 * ESLint configuration (flat config).
 *
 * Type-aware linting is enabled: `recommendedTypeChecked` catches the class of
 * mistake that plain syntactic rules cannot see - a forgotten `await`, a promise
 * passed where a value was expected, an `any` leaking out of a cast.
 */
export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'coverage', 'src/types/api.d.ts'] },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // An unused variable prefixed with _ is a documented intention, not an
      // oversight - typically an ignored callback argument.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // Consistent type imports keep `verbatimModuleSyntax` happy and make it
      // obvious which imports vanish at build time.
      '@typescript-eslint/consistent-type-imports': [
        'error',
        { prefer: 'type-imports', fixStyle: 'inline-type-imports' },
      ],
      // Errors, not warnings: an unhandled promise in a React event handler fails
      // silently in the browser, which is the worst possible failure mode.
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': 'error',
    },
  },
  {
    // Test files legitimately do things the app should not.
    files: ['**/*.test.{ts,tsx}', 'src/test/**'],
    rules: {
      '@typescript-eslint/no-non-null-assertion': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
    },
  },
  {
    // Build tooling runs in Node, not the browser.
    files: ['vite.config.ts', 'vitest.config.ts', 'eslint.config.js'],
    languageOptions: { globals: globals.node },
  },
  {
    // This config file is not part of a TypeScript project, so the type-aware
    // rules have no type information to work from and error out. Disabling them
    // for plain JS keeps type-aware linting on everywhere it can actually run.
    files: ['**/*.js'],
    extends: [tseslint.configs.disableTypeChecked],
  },
);
