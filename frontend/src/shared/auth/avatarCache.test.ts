import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { SessionIdentity } from './session';
import { readCachedAvatarUrl, storeCachedAvatarUrl } from './avatarCache';

const identity: SessionIdentity = {
  id: 'identity-1',
  subject_id: 'subject-1',
  tenant_id: 'tenant-1',
  username: 'reader@example.com',
  display_name: 'Reader',
  avatar_url: '/profile?avatar_key=avatar-1',
  auth_type: 'cloudbase',
  auth_providers: ['email'],
  membership: 'free',
  roles: [],
};

describe('local avatar cache', () => {
  const values = new Map<string, string>();
  const localStorage = {
    getItem: (key: string) => values.get(key) ?? null,
    removeItem: (key: string) => values.delete(key),
    setItem: (key: string, value: string) => values.set(key, value),
  };

  beforeEach(() => {
    values.clear();
    vi.stubGlobal('window', { dispatchEvent: vi.fn() });
    vi.stubGlobal('localStorage', localStorage);
    vi.stubGlobal('CustomEvent', class CustomEvent { constructor(public type: string) {} });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('returns a local data URL immediately for the matching account and source', () => {
    const dataUrl = 'data:image/webp;base64,avatar';
    expect(storeCachedAvatarUrl(identity, dataUrl)).toBe(dataUrl);
    expect(readCachedAvatarUrl(identity)).toBe(dataUrl);
  });

  it('does not reuse stale avatar bytes after the server URL changes', () => {
    storeCachedAvatarUrl(identity, 'data:image/webp;base64,old');
    expect(readCachedAvatarUrl({ ...identity, avatar_url: '/profile?avatar_key=avatar-2' })).toBe('');
  });

  it('never caches an avatar for a guest', () => {
    expect(storeCachedAvatarUrl({ ...identity, auth_type: 'guest' }, 'data:image/webp;base64,x')).toBe('');
  });
});
