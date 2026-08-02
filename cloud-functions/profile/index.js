import { getStore } from '@edgeone/pages-blob';

import {
  currentUser,
  readBearerToken,
  sessionCookie,
  signSessionToken,
} from '../../auth/session.js';
import {
  applyProfile,
  loadProfile,
  profileAvatarPrefix,
  saveProfile,
} from '../../auth/profile.js';
import {
  MOBILE_ACCESS_TTL_SECONDS,
  USER_SESSION_TTL_SECONDS,
} from '../../auth/controllers/cloudbase-controller.js';

const MAX_AVATAR_BYTES = 5 * 1024 * 1024;
const AVATAR_TYPES = new Map([
  ['image/png', '.png'],
  ['image/jpeg', '.jpg'],
  ['image/webp', '.webp'],
]);

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      ...headers,
    },
  });
}

function sessionPayload(identity) {
  return {
    sub: identity.subject_id,
    tenant_id: identity.tenant_id,
    username: identity.username,
    display_name: identity.display_name,
    avatar_url: identity.avatar_url,
    auth_type: identity.auth_type,
    auth_providers: identity.auth_providers,
    membership: identity.membership,
    roles: identity.roles,
    session_version: identity.session_version,
  };
}

function validAvatarMetadata(metadata) {
  const contentType = String(metadata?.contentType || '');
  const size = Number(
    metadata?.size
    || metadata?.contentLength
    || metadata?.headers?.['content-length']
    || 0,
  );
  return AVATAR_TYPES.has(contentType)
    && Number.isFinite(size)
    && size > 0
    && size <= MAX_AVATAR_BYTES;
}

async function avatarResponse(request, store, identity, key) {
  if (!key.startsWith(profileAvatarPrefix(identity))) {
    return json({ error: 'Invalid avatar key' }, 400);
  }
  const metadata = await store.getMetadata(key);
  if (!metadata) return json({ error: 'Avatar not found' }, 404);
  const contentType = String(metadata.contentType || 'image/png');
  if (!validAvatarMetadata(metadata)) return json({ error: 'Invalid avatar object' }, 415);
  if (request.method === 'HEAD') {
    return new Response(null, {
      headers: { 'Content-Type': contentType, 'Cache-Control': 'private, max-age=300' },
    });
  }
  const body = await store.get(key, { type: 'arrayBuffer', consistency: 'strong' });
  return new Response(body, {
    headers: { 'Content-Type': contentType, 'Cache-Control': 'private, max-age=300' },
  });
}

export async function onRequest(context) {
  const { request, env = {} } = context;
  let identity;
  try {
    identity = await currentUser(request, env);
  } catch {
    return json({ error: 'Unauthorized' }, 401);
  }
  if (identity.auth_type === 'guest') return json({ error: 'Login required' }, 403);
  const store = context.__store || getStore({ name: 'yuanbao-files', consistency: 'strong' });
  const url = new URL(request.url);
  const avatarKey = url.searchParams.get('avatar_key') || '';
  if ((request.method === 'GET' || request.method === 'HEAD') && avatarKey) {
    return avatarResponse(request, store, identity, avatarKey);
  }
  if (request.method === 'GET') {
    return json({ profile: applyProfile(identity, await loadProfile(store, identity)) });
  }
  if (request.method !== 'POST') return json({ error: 'Method not allowed' }, 405);

  const body = await request.json().catch(() => ({}));
  const operation = String(body.operation || 'update');
  if (operation === 'create_avatar_upload') {
    const contentType = String(body.content_type || '');
    const size = Number(body.size || 0);
    const extension = AVATAR_TYPES.get(contentType);
    if (!extension) return json({ error: 'Only PNG, JPEG and WebP avatars are supported' }, 415);
    if (!Number.isFinite(size) || size <= 0 || size > MAX_AVATAR_BYTES) {
      return json({ error: 'Avatar must be between 1B and 5MB' }, 400);
    }
    const key = `${profileAvatarPrefix(identity)}${crypto.randomUUID()}${extension}`;
    const upload = await store.createUploadUrl(key, { expireSeconds: 600, contentType });
    return json({
      ...upload,
      key,
      content_url: `/profile?avatar_key=${encodeURIComponent(key)}`,
    });
  }
  if (operation !== 'update') return json({ error: 'Unknown operation' }, 400);

  const displayName = String(body.display_name || '').trim().slice(0, 120);
  if (!displayName) return json({ error: 'Display name is required' }, 400);
  let avatarUrl = String(identity.avatar_url || '').slice(0, 1000);
  const uploadedKey = String(body.avatar_key || '');
  if (uploadedKey) {
    if (!uploadedKey.startsWith(profileAvatarPrefix(identity))) {
      return json({ error: 'Invalid avatar key' }, 400);
    }
    const metadata = await store.getMetadata(uploadedKey);
    if (!validAvatarMetadata(metadata)) {
      return json({ error: 'Avatar upload is incomplete' }, 400);
    }
    avatarUrl = `/profile?avatar_key=${encodeURIComponent(uploadedKey)}`;
  }
  const profile = await saveProfile(store, identity, {
    display_name: displayName,
    avatar_url: avatarUrl,
  });
  const updatedIdentity = applyProfile(identity, profile);
  const nativeClient = Boolean(readBearerToken(request.headers));
  const ttl = nativeClient ? MOBILE_ACCESS_TTL_SECONDS : USER_SESSION_TTL_SECONDS;
  const token = await signSessionToken(
    {
      ...sessionPayload(updatedIdentity),
      ...(nativeClient ? { client_kind: 'native' } : {}),
    },
    env,
    ttl,
  );
  return json({
    ok: true,
    identity: updatedIdentity,
    ...(nativeClient ? {
      access_token: token,
      token_type: 'Bearer',
      expires_in: ttl,
    } : {}),
  }, 200, nativeClient ? {} : {
    'Set-Cookie': sessionCookie(token, { maxAge: ttl }),
  });
}
