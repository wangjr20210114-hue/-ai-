import { describe, expect, it } from 'vitest';

import type { AuthSession } from '../../../shared/auth/session';
import type { SkillMarketplaceState } from './types';
import { marketplaceAccount, syncMarketplaceAuth } from './authSync';

function cloudBaseSession(): AuthSession {
  return {
    identity: {
      id: 'floris:user-1', subject_id: 'user-1', tenant_id: 'floris', username: 'user',
      display_name: 'Floris user', avatar_url: '', auth_type: 'cloudbase',
      auth_providers: ['email'], membership: 'free', roles: ['user'],
    },
    entitlements: {
      plan: 'free', limits: { userSkillUploads: 2 }, payment_available: false,
    },
    login: {
      cloudbase_available: true, cloudbase_session_url: '', wechat_available: false,
      wechat_mode: 'qr', wechat_start_url: '', logout_url: '',
    },
  };
}

describe('Skills marketplace auth synchronization', () => {
  it('replaces a visible guest identity immediately after CloudBase login', () => {
    const current = {
      identity: {
        user_id: 'guest', subject_id: 'guest', tenant_id: 'floris', display_name: 'Guest',
        avatar_url: '', auth_type: 'guest', membership: 'guest', roles: ['guest'],
      },
      entitlements: { plan: 'guest', limits: {}, payment_available: false },
    } as SkillMarketplaceState;
    const session = cloudBaseSession();

    const updated = syncMarketplaceAuth(current, session);
    expect(updated?.identity.auth_type).toBe('cloudbase');
    expect(updated?.identity.display_name).toBe('Floris user');
    expect(updated?.entitlements.plan).toBe('free');
    expect(updated?.entitlements.limits.userSkillUploads).toBe(2);
  });

  it('keeps the signed account visible while marketplace state is unavailable', () => {
    const account = marketplaceAccount(null, cloudBaseSession());
    expect(account.identity?.auth_type).toBe('cloudbase');
    expect(account.identity?.display_name).toBe('Floris user');
    expect(account.plan).toBe('free');
  });
});
