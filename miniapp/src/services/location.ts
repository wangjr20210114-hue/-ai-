import Taro from '@tarojs/taro'

export type MiniappLocationResult = {
  location?: {
    latitude: number
    longitude: number
    accuracy_meters: number
    captured_at: number
    coordinate_type: 'wgs84'
  }
  request: { state: 'available' | 'denied' | 'timed_out' | 'unavailable' | 'failed'; attempted_at: number }
}

export async function requestCurrentLocation(): Promise<MiniappLocationResult> {
  const attemptedAt = Date.now()
  try {
    const result = await Taro.getLocation({ type: 'wgs84', isHighAccuracy: false })
    return {
      location: {
        latitude: result.latitude,
        longitude: result.longitude,
        accuracy_meters: Math.max(0, Number(result.accuracy || 0)),
        captured_at: attemptedAt,
        coordinate_type: 'wgs84',
      },
      request: { state: 'available', attempted_at: attemptedAt },
    }
  } catch (error) {
    const message = String((error as { errMsg?: string })?.errMsg || error)
    const state = /deny|denied|auth/i.test(message)
      ? 'denied'
      : /timeout/i.test(message)
        ? 'timed_out'
        : /unavailable/i.test(message)
          ? 'unavailable'
          : 'failed'
    return { request: { state, attempted_at: attemptedAt } }
  }
}
