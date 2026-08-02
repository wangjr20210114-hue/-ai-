import type { SessionIdentity } from './session';

const AVATAR_CACHE_PREFIX = 'floris.auth.avatar.v1.';
const AVATAR_CACHE_EVENT = 'floris:avatar-cached';
const AVATAR_EDGE_PX = 192;
const AVATAR_WEBP_QUALITY = 0.82;

type AvatarIdentity = Pick<SessionIdentity, 'auth_type' | 'avatar_url' | 'subject_id'>;

type CachedAvatar = {
  dataUrl: string;
  sourceUrl: string;
};

const inFlight = new Map<string, Promise<string>>();

function cacheKey(subjectId: string): string {
  return `${AVATAR_CACHE_PREFIX}${encodeURIComponent(subjectId)}`;
}

function isCacheable(identity?: AvatarIdentity | null): identity is AvatarIdentity {
  return Boolean(
    identity
    && identity.auth_type !== 'guest'
    && identity.subject_id
    && identity.avatar_url,
  );
}

export function readCachedAvatarUrl(identity?: AvatarIdentity | null): string {
  if (typeof window === 'undefined' || !isCacheable(identity)) return '';
  try {
    const cached = JSON.parse(localStorage.getItem(cacheKey(identity.subject_id)) || 'null') as CachedAvatar | null;
    if (cached?.sourceUrl !== identity.avatar_url || !cached.dataUrl?.startsWith('data:image/')) return '';
    return cached.dataUrl;
  } catch {
    return '';
  }
}

export function storeCachedAvatarUrl(identity: AvatarIdentity, dataUrl: string): string {
  if (typeof window === 'undefined' || !isCacheable(identity) || !dataUrl.startsWith('data:image/')) return '';
  try {
    localStorage.setItem(cacheKey(identity.subject_id), JSON.stringify({
      dataUrl,
      sourceUrl: identity.avatar_url,
    } satisfies CachedAvatar));
    window.dispatchEvent(new CustomEvent(AVATAR_CACHE_EVENT, {
      detail: { subjectId: identity.subject_id },
    }));
    return dataUrl;
  } catch {
    return '';
  }
}

async function optimizedDataUrl(blob: Blob): Promise<string> {
  const objectUrl = URL.createObjectURL(blob);
  try {
    const image = new Image();
    image.decoding = 'async';
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error('Avatar could not be decoded'));
      image.src = objectUrl;
    });
    const scale = Math.min(1, AVATAR_EDGE_PX / Math.max(image.naturalWidth, image.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    const context = canvas.getContext('2d');
    if (!context) return '';
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/webp', AVATAR_WEBP_QUALITY);
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export async function cacheAvatarBlob(identity: AvatarIdentity, blob: Blob): Promise<string> {
  if (!isCacheable(identity) || !blob.type.startsWith('image/')) return '';
  const dataUrl = await optimizedDataUrl(blob);
  return dataUrl ? storeCachedAvatarUrl(identity, dataUrl) : '';
}

export function warmAvatarCache(identity?: AvatarIdentity | null): Promise<string> {
  if (!isCacheable(identity)) return Promise.resolve('');
  const cached = readCachedAvatarUrl(identity);
  if (cached) return Promise.resolve(cached);
  const key = `${identity.subject_id}\n${identity.avatar_url}`;
  const pending = inFlight.get(key);
  if (pending) return pending;
  const request = fetch(identity.avatar_url, {
    credentials: 'same-origin',
    headers: { Accept: 'image/avif,image/webp,image/png,image/jpeg' },
  }).then(async (response) => {
    if (!response.ok) return '';
    return cacheAvatarBlob(identity, await response.blob());
  }).catch(() => '').finally(() => inFlight.delete(key));
  inFlight.set(key, request);
  return request;
}

export const avatarCacheEvent = AVATAR_CACHE_EVENT;
export type { AvatarIdentity };
