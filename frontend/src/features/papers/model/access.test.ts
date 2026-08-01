import { describe, expect, it } from 'vitest';

import type { AuthSession } from '../../../shared/auth/session';
import { readingAccess } from './access';

function session(authType: AuthSession['identity']['auth_type']): AuthSession {
  return {
    identity: {
      id: 'floris:user',
      subject_id: 'user',
      tenant_id: 'floris',
      username: 'user',
      display_name: 'User',
      avatar_url: '',
      auth_type: authType,
      auth_providers: [],
      membership: authType === 'guest' ? 'guest' : 'free',
      roles: [authType === 'guest' ? 'guest' : 'user'],
    },
    entitlements: { plan: authType === 'guest' ? 'guest' : 'free', limits: {}, payment_available: false },
    login: {
      cloudbase_available: true,
      cloudbase_session_url: '/auth/cloudbase/session',
      wechat_available: false,
      wechat_mode: 'qr',
      wechat_start_url: '/auth/wechat/start',
      logout_url: '/auth/logout',
    },
  };
}

describe('readingAccess', () => {
  it('waits for the session before making a protected request', () => {
    expect(readingAccess(null)).toBe('loading');
  });

  it('degrades guests to a login call-to-action', () => {
    expect(readingAccess(session('guest'))).toBe('login_required');
  });

  it('allows every configured signed-in provider', () => {
    expect(readingAccess(session('cloudbase'))).toBe('available');
    expect(readingAccess(session('wechat'))).toBe('available');
  });
});
