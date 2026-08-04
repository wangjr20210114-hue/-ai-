import { describe, expect, it, vi } from 'vitest';

import { translate } from '../../i18n';

function sessionPayload(authType: 'guest' | 'cloudbase') {
  return {
    identity: {
      id: `${authType}:subject`, subject_id: 'subject', tenant_id: 'floris',
      username: authType, display_name: authType, avatar_url: '', auth_type: authType,
      auth_providers: [], membership: authType === 'guest' ? 'guest' : 'free', roles: [],
    },
    entitlements: { plan: authType === 'guest' ? 'guest' : 'free', limits: {}, payment_available: false },
    login: {
      cloudbase_available: true, cloudbase_session_url: '/auth/cloudbase/session',
      wechat_available: false, wechat_mode: 'qr', wechat_start_url: '/auth/wechat/start',
      logout_url: '/auth/logout',
    },
  };
}

describe('shared auth session refresh', () => {
  it('does not let a late guest bootstrap overwrite a completed login refresh', async () => {
    vi.resetModules();
    let resolveGuest: ((response: Response) => void) | undefined;
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    fetchMock
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveGuest = resolve; }))
      .mockResolvedValueOnce(new Response(JSON.stringify(sessionPayload('cloudbase')), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));

    const session = await import('./session');
    const stale = session.ensureAuthSession();
    const fresh = await session.ensureAuthSession(true);

    expect(fresh.identity.auth_type).toBe('cloudbase');
    resolveGuest?.(new Response(JSON.stringify(sessionPayload('guest')), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    await expect(stale).rejects.toThrow(translate('staleAuthSession'));
    expect(session.currentAuthSession()?.identity.auth_type).toBe('cloudbase');
  });
});
