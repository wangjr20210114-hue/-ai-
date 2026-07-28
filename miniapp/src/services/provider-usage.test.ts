import { describe, expect, it, vi } from 'vitest'

vi.mock('./request', () => ({ apiRequest: vi.fn() }))
import { meteredProviderValue, type ProviderUsageSummary } from './provider-usage'

describe('provider usage helpers', () => {
  it('adds the selected metric across providers without mixing other counters', () => {
    const usage = {
      metering: {
        daily: {
          'hunyuan.vision_tokens': 12,
          'cloudflare.vision_tokens': 8,
          'wsa.requests': 4,
        },
        monthly: {},
      },
    } as unknown as ProviderUsageSummary
    expect(meteredProviderValue(usage, 'daily', 'vision_tokens')).toBe(20)
    expect(meteredProviderValue(usage, 'daily', 'requests')).toBe(4)
  })
})
