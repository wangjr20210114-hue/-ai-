import Taro from '@tarojs/taro'

/**
 * Local copy of the user's WeChat profile (avatar + nickname), collected via
 * the official "avatar & nickname fill-in" capability: chooseAvatar button +
 * nickname input. getUserProfile/getUserInfo only return anonymous data on
 * current base libraries, so we never call them.
 */

export interface UserProfile {
  avatarUrl: string
  nickName: string
}

const PROFILE_KEY = 'floris.miniapp.profile.v1'
const AVATAR_EVENT = 'floris:profile-updated'

export function readProfile(): UserProfile {
  try {
    const cached = Taro.getStorageSync(PROFILE_KEY)
    if (cached && typeof cached === 'object') {
      const profile = cached as Partial<UserProfile>
      return {
        avatarUrl: typeof profile.avatarUrl === 'string' ? profile.avatarUrl : '',
        nickName: typeof profile.nickName === 'string' ? profile.nickName : '',
      }
    }
  } catch {
    // Storage misses must never break rendering.
  }
  return { avatarUrl: '', nickName: '' }
}

function writeProfile(profile: UserProfile): UserProfile {
  try {
    Taro.setStorageSync(PROFILE_KEY, profile)
    Taro.eventCenter.trigger(AVATAR_EVENT, profile)
  } catch {
    // Non-fatal: the next launch simply asks again.
  }
  return profile
}

export function saveNickName(nickName: string): UserProfile {
  const current = readProfile()
  return writeProfile({ ...current, nickName: nickName.trim() })
}

/**
 * chooseAvatar returns a short-lived temp path. Persist it into the local
 * file system so the avatar survives relaunches; fall back to the temp path
 * when persistence is unavailable (still works for the current session).
 */
export async function saveAvatarFromChoose(tempAvatarUrl: string): Promise<UserProfile> {
  const current = readProfile()
  if (!tempAvatarUrl) return current
  let persisted = tempAvatarUrl
  try {
    const result = await new Promise<{ savedFilePath?: string }>((resolve) => {
      Taro.getFileSystemManager().saveFile({
        tempFilePath: tempAvatarUrl,
        success: (res) => resolve(res as { savedFilePath?: string }),
        fail: () => resolve({}),
      })
    })
    if (result.savedFilePath) persisted = result.savedFilePath
  } catch {
    // Keep the temp path; better than losing the avatar entirely.
  }
  return writeProfile({ ...current, avatarUrl: persisted })
}

export function subscribeProfile(listener: (profile: UserProfile) => void): () => void {
  Taro.eventCenter.on(AVATAR_EVENT, listener)
  return () => Taro.eventCenter.off(AVATAR_EVENT, listener)
}
