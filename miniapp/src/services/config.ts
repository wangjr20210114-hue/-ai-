const configuredBaseUrl = String(process.env.TARO_APP_API_BASE_URL || '').trim()

export const API_BASE_URL = (configuredBaseUrl || 'https://miniapp-floris.jlutx.com').replace(/\/+$/, '')

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}
