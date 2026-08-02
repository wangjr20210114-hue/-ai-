import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  consumeAccountChooserRequest,
  requestAccountChooserAfterReload,
} from './loginIntent';

describe('login navigation intent', () => {
  const values = new Map<string, string>();
  const sessionStorage = {
    clear: () => values.clear(),
    getItem: (key: string) => values.get(key) ?? null,
    removeItem: (key: string) => values.delete(key),
    setItem: (key: string, value: string) => values.set(key, value),
  };

  beforeEach(() => {
    values.clear();
    vi.stubGlobal('window', { sessionStorage });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('opens the account chooser once after switching', () => {
    requestAccountChooserAfterReload();
    expect(consumeAccountChooserRequest()).toBe(true);
    expect(consumeAccountChooserRequest()).toBe(false);
  });
});
