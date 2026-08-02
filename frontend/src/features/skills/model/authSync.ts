import type { AuthSession } from '../../../shared/auth/session';
import type { SkillMarketplaceState } from '../../../shared/types';

export function marketplaceAccount(
  current: SkillMarketplaceState | null,
  session: AuthSession | null,
) {
  return {
    identity: session?.identity || current?.identity || null,
    plan: session?.entitlements.plan || current?.entitlements.plan || null,
  };
}

export function syncMarketplaceAuth(
  current: SkillMarketplaceState | null,
  session: AuthSession,
): SkillMarketplaceState | null {
  if (!current) return current;
  const limits = Object.fromEntries(
    Object.entries(session.entitlements.limits)
      .filter((entry): entry is [string, string | number] => (
        typeof entry[1] === 'string' || typeof entry[1] === 'number'
      )),
  );
  return {
    ...current,
    entitlements: {
      ...current.entitlements,
      plan: session.entitlements.plan,
      payment_available: session.entitlements.payment_available,
      limits,
    },
    identity: {
      ...current.identity,
      user_id: session.identity.id,
      subject_id: session.identity.subject_id,
      tenant_id: session.identity.tenant_id,
      display_name: session.identity.display_name,
      avatar_url: session.identity.avatar_url,
      auth_type: session.identity.auth_type,
      membership: session.identity.membership,
      roles: session.identity.roles,
    },
  };
}
