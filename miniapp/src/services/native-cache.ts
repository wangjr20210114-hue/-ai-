import Taro from '@tarojs/taro'

type NativeCacheEnvelope<T> = {
  savedAt: number
  value: T
}

/**
 * Small stale-while-revalidate snapshots backed by WeChat's native storage.
 * Makers remains authoritative; this only prevents tab navigation from
 * rendering an empty screen while the same data is fetched again.
 */
export function readNativeCache<T>(key: string, maxAgeMs = 24 * 60 * 60_000): T | null {
  try {
    const cached = Taro.getStorageSync<NativeCacheEnvelope<T>>(key)
    if (!cached || typeof cached.savedAt !== 'number' || cached.value === undefined) return null
    if (Date.now() - cached.savedAt > maxAgeMs) return null
    return cached.value
  } catch {
    return null
  }
}

export function writeNativeCache<T>(key: string, value: T): void {
  try {
    Taro.setStorageSync(key, {
      savedAt: Date.now(),
      value,
    } satisfies NativeCacheEnvelope<T>)
  } catch {
    // Storage pressure must not break the online path.
  }
}
