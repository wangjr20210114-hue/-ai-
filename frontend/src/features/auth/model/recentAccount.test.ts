import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { SessionIdentity } from '../../../shared/auth/session';
import {
  clearExpiredRecentAccount,
  readRecentAccount,
  rememberRecentAccount,
} from './recentAccount';

const signedIdentity: SessionIdentity = {
  id: 'identity-1',
  subject_id: 'subject-1',
  tenant_id: 'tenant-1',
  username: 'reader@example.com',
  display_name: '橘子读者',
  avatar_url: 'https://example.com/avatar.png',
  auth_type: 'cloudbase',
  auth_providers: ['email'],
  membership: 'free',
  roles: [],
};

describe('recent account metadata', () => {
  const values = new Map<string, string>();
  const storage = {
    clear: () => values.clear(),
    getItem: (key: string) => values.get(key) ?? null,
    removeItem: (key: string) => values.delete(key),
    setItem: (key: string, value: string) => values.set(key, value),
  };

  beforeEach(() => {
    values.clear();
    vi.stubGlobal('window', {});
    vi.stubGlobal('localStorage', storage);
  });

  afterEach(() => vi.unstubAllGlobals());

  it('keeps only display metadata needed by the account chooser', () => {
    rememberRecentAccount(signedIdentity);

    expect(readRecentAccount()).toEqual({
      avatarUrl: 'https://example.com/avatar.png',
      displayName: '橘子读者',
      subjectId: 'subject-1',
    });
  });

  it('never stores a guest as a resumable account', () => {
    rememberRecentAccount({ ...signedIdentity, auth_type: 'guest' });
    expect(readRecentAccount()).toBeNull();
  });

  it('removes chooser metadata after the resumable session expires', () => {
    rememberRecentAccount(signedIdentity);
    clearExpiredRecentAccount();
    expect(readRecentAccount()).toBeNull();
  });
});
