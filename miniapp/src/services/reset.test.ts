import { beforeEach, describe, expect, it, vi } from 'vitest'

const storage = new Map<string, unknown>()
vi.mock('@tarojs/taro', () => ({
  default: {
    clearStorageSync: vi.fn(() => storage.clear()),
    setStorageSync: vi.fn((key: string, value: unknown) => storage.set(key, value)),
  },
}))

import { clearMiniappLocalData } from './reset'

describe('mini-program reset', () => {
  beforeEach(() => {
    storage.clear()
    storage.set('messages', ['old'])
  })

  it('clears local workspace data while preserving the selected language', () => {
    clearMiniappLocalData('en')
    expect(storage.get('messages')).toBeUndefined()
    expect(storage.get('floris-language')).toBe('en')
  })
})
