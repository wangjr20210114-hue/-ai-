import { useEffect, useMemo, useState } from 'react';

import {
  avatarCacheEvent,
  readCachedAvatarUrl,
  warmAvatarCache,
  type AvatarIdentity,
} from './avatarCache';

const DEFAULT_AVATAR_URL = '/default-user-avatar-anime.png';

function resolvedAvatarUrl(identity?: AvatarIdentity | null): string {
  return readCachedAvatarUrl(identity) || identity?.avatar_url || DEFAULT_AVATAR_URL;
}

export function useAvatarUrl(identity?: AvatarIdentity | null): string {
  const [, setRevision] = useState(0);
  const subjectId = identity?.subject_id || '';
  const sourceUrl = identity?.avatar_url || '';
  const authType = identity?.auth_type || 'guest';
  const stableIdentity = useMemo<AvatarIdentity | null>(() => (
    subjectId ? { auth_type: authType, avatar_url: sourceUrl, subject_id: subjectId } : null
  ), [authType, sourceUrl, subjectId]);

  useEffect(() => {
    void warmAvatarCache(stableIdentity).then((cached) => {
      if (cached) setRevision((value) => value + 1);
    });
  }, [stableIdentity]);

  useEffect(() => {
    const changed = (event: Event) => {
      const changedSubject = (event as CustomEvent<{ subjectId?: string }>).detail?.subjectId;
      if (!changedSubject || changedSubject === subjectId) setRevision((value) => value + 1);
    };
    window.addEventListener(avatarCacheEvent, changed);
    return () => window.removeEventListener(avatarCacheEvent, changed);
  }, [subjectId]);

  return resolvedAvatarUrl(stableIdentity);
}
