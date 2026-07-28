import { beforeEach, describe, expect, it, vi } from 'vitest'

const storage = new Map<string, unknown>()

vi.mock('@tarojs/taro', () => ({
  default: {
    getStorageSync: (key: string) => storage.get(key),
    setStorageSync: (key: string, value: unknown) => storage.set(key, value),
  },
}))

import { readNativeCache, writeNativeCache } from './native-cache'

describe('native cache', () => {
  beforeEach(() => storage.clear())

  it('round-trips a native stale-while-revalidate snapshot', () => {
    writeNativeCache('screen', { value: 7 })
    expect(readNativeCache<{ value: number }>('screen')).toEqual({ value: 7 })
  })

  it('ignores stale snapshots', () => {
    storage.set('screen', { savedAt: Date.now() - 2_000, value: { value: 7 } })
    expect(readNativeCache('screen', 1_000)).toBeNull()
  })
})
