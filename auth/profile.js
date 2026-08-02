import { tenantPrefix } from './session.js';

export const DEFAULT_USER_AVATAR_URL = '/default-user-avatar-anime.png';

export function profileKey(identity) {
  return `${tenantPrefix(identity)}profile/current.json`;
}

export function profileAvatarPrefix(identity) {
  return `${tenantPrefix(identity)}profile/avatars/`;
}

export async function loadProfile(store, identity) {
  if (!store || identity?.auth_type === 'guest') return null;
  try {
    const value = await store.get(profileKey(identity), {
      type: 'json',
      consistency: 'strong',
    });
    return value && typeof value === 'object' ? value : null;
  } catch {
    return null;
  }
}

export async function saveProfile(store, identity, profile) {
  const value = {
    schema_version: 1,
    display_name: String(profile?.display_name || identity.display_name || '').trim().slice(0, 120),
    avatar_url: String(profile?.avatar_url || identity.avatar_url || '').trim().slice(0, 1000),
    updated_at: Date.now(),
  };
  await store.setJSON(profileKey(identity), value);
  return value;
}

export function applyProfile(identity, profile) {
  if (!profile || identity?.auth_type === 'guest') return identity;
  return {
    ...identity,
    display_name: String(profile.display_name || identity.display_name || '').slice(0, 120),
    avatar_url: String(profile.avatar_url || identity.avatar_url || '').slice(0, 1000),
  };
}
