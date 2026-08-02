import { ensureAuthSession, type AuthSession } from '../../../shared/auth/session';
import { requestJson, requestRaw } from '../../../shared/transport/httpClient';

interface AvatarUpload {
  url: string;
  key: string;
}

export async function updateAccountProfile(
  displayName: string,
  avatar?: File | null,
): Promise<AuthSession> {
  let avatarKey = '';
  if (avatar) {
    const upload = await requestJson<AvatarUpload>('/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        operation: 'create_avatar_upload',
        content_type: avatar.type,
        size: avatar.size,
      }),
    });
    const stored = await requestRaw(upload.url, {
      method: 'PUT',
      headers: { 'Content-Type': avatar.type },
      body: avatar,
    }, false);
    if (!stored.ok) throw new Error('Could not upload avatar');
    avatarKey = upload.key;
  }
  await requestJson('/profile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      operation: 'update',
      display_name: displayName,
      ...(avatarKey ? { avatar_key: avatarKey } : {}),
    }),
  });
  return ensureAuthSession(true);
}
