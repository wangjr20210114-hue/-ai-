import { describe, expect, it } from 'vitest';
import { isAppSession } from './auth';

describe('isAppSession', () => {
  it('accepts a complete Makers session', () => {
    expect(isAppSession({
      mode: 'multi_user',
      user: { id: 'user-1', username: 'demo', roles: ['user'] },
    })).toBe(true);
  });

  it('rejects an SPA fallback or incomplete identity response', () => {
    expect(isAppSession({})).toBe(false);
    expect(isAppSession({ mode: 'single_user', user: undefined })).toBe(false);
    expect(isAppSession({ mode: 'single_user', user: { id: '', username: 'demo', roles: [] } })).toBe(false);
  });
});
