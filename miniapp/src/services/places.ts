import { apiRequest } from './request'

export interface VerifiedPlace {
  place_id: string
  name: string
  address?: string
  latitude: number
  longitude: number
  category?: string
  distance?: number
}

export async function searchVerifiedPlaces(
  conversationId: string,
  query: string,
  city = '',
): Promise<VerifiedPlace[]> {
  const data = await apiRequest<{ places?: VerifiedPlace[] }>('/places', {
    method: 'POST',
    conversationId,
    data: { query, ...(city ? { city } : {}), limit: 10 },
    timeout: 35_000,
  })
  return data.places || []
}
