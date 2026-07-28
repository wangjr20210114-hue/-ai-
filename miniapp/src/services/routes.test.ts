import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  apiRequest: vi.fn(),
}))

vi.mock('./request', () => ({
  apiRequest: mocks.apiRequest,
}))

import {
  orderedRoutePayload,
  planOrderedRoute,
  validRoutePlaces,
  type RoutePlace,
} from './routes'

const stops: RoutePlace[] = [
  { place_id: 'breakfast', name: '早餐店', address: '海淀区', latitude: 39.1, longitude: 116.1 },
  { place_id: 'beijing-station', name: '北京站', address: '东城区', latitude: 39.2, longitude: 116.2 },
  { place_id: 'hotel', name: '锦江之星', address: '丰台区', latitude: 39.3, longitude: 116.3 },
]

describe('native map route bridge', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.apiRequest.mockResolvedValue({ route: { distance_meters: 1234 } })
  })

  it('preserves the Agent-frozen stop order and explicitly disables optimization', () => {
    const payload = orderedRoutePayload(stops, 'driving', 'least_time')
    expect(payload.places.map((place) => place.place_id)).toEqual([
      'breakfast',
      'beijing-station',
      'hotel',
    ])
    expect(payload).toMatchObject({
      mode: 'driving',
      strategy: 'least_time',
      optimize: false,
    })
    expect(payload.places).not.toBe(stops)
  })

  it('drops only invalid coordinates without reordering verified places', () => {
    expect(validRoutePlaces([
      stops[0],
      { name: '无坐标地点', latitude: Number.NaN, longitude: 116.2 },
      stops[1],
      { name: '越界地点', latitude: 91, longitude: 116.4 },
      stops[2],
    ]).map((place) => place.place_id)).toEqual([
      'breakfast',
      'beijing-station',
      'hotel',
    ])
  })

  it('reuses the existing Makers routes endpoint without client-side planning', async () => {
    await planOrderedRoute('yb7_test', stops, 'transit')
    expect(mocks.apiRequest).toHaveBeenCalledWith('/routes', {
      method: 'POST',
      conversationId: 'yb7_test',
      data: {
        places: stops,
        mode: 'transit',
        optimize: false,
      },
      timeout: 30_000,
    })
  })
})
