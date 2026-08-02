import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  consumeAccountChooserRequest,
  consumeOAuthLoginIntent,
  markOAuthLoginIntent,
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

  it('restores automatically only for a fresh OAuth callback', () => {
    markOAuthLoginIntent(1_000);
    expect(consumeOAuthLoginIntent(1_500)).toBe(true);
    expect(consumeOAuthLoginIntent(1_500)).toBe(false);
  });

  it('rejects an expired OAuth callback intent', () => {
    markOAuthLoginIntent(1_000);
    expect(consumeOAuthLoginIntent(16 * 60 * 1000)).toBe(false);
  });

  it('opens the account chooser once after switching', () => {
    requestAccountChooserAfterReload();
    expect(consumeAccountChooserRequest()).toBe(true);
    expect(consumeAccountChooserRequest()).toBe(false);
  });
});
