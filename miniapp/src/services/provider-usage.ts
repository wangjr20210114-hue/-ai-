import { apiRequest } from './request'

export interface ProviderUsageSummary {
  refreshed_at: number
  usage: {
    daily_tokens: number
    monthly_tokens: number
  }
  metering: {
    daily: Record<string, number>
    monthly: Record<string, number>
  }
  providers: Array<{
    id: string
    configured: boolean
    is_available: boolean
    balances: Array<{
      currency: string
      total_balance: number | string
    }>
  }>
}

export function getProviderUsage(conversationId: string): Promise<ProviderUsageSummary> {
  return apiRequest<ProviderUsageSummary>('/provider_usage', {
    conversationId,
    timeout: 20_000,
  })
}

export function meteredProviderValue(
  usage: ProviderUsageSummary | null,
  period: 'daily' | 'monthly',
  metric: string,
): number {
  return Object.entries(usage?.metering?.[period] || {})
    .reduce((total, [key, value]) => (
      total + (key.endsWith(`.${metric}`) ? Number(value) || 0 : 0)
    ), 0)
}
