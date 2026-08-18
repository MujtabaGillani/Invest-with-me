/**
 * Vitest setup, loaded before every test file.
 *
 * Adds jest-dom's matchers (`toBeInTheDocument`, `toHaveTextContent`) and clears
 * mocks between tests so state cannot leak from one case to the next.
 */

import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
