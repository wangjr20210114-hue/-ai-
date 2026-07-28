export interface ImageVersion {
  id: string
  prompt: string
  image_url: string
  storage_key?: string
  parent_action_id?: string
  created_at?: number
}

interface ImageActionLike {
  id: string
  payload?: unknown
  result?: unknown
  created_at?: number
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

/**
 * Normalises the image version chain returned by the existing Makers workspace.
 * Both the web client and the WeChat client use this function so image history
 * stays a presentation concern rather than becoming a second business workflow.
 */
export function imageVersionsFrom(action: ImageActionLike): ImageVersion[] {
  const payload = record(action.payload)
  const result = record(action.result)
  const rawVersions = Array.isArray(result.versions) ? result.versions : []
  const versions = rawVersions
    .map(record)
    .filter((item) => Boolean(item.id && item.image_url))
    .map((item) => ({
      id: String(item.id),
      prompt: String(item.prompt || ''),
      image_url: String(item.image_url),
      storage_key: String(item.storage_key || ''),
      parent_action_id: String(item.parent_action_id || ''),
      created_at: Number(item.created_at || 0),
    }))
  if (versions.length) return versions
  if (!result.image_url) return []
  return [{
    id: action.id,
    prompt: String(payload.prompt || ''),
    image_url: String(result.image_url),
    storage_key: String(result.storage_key || ''),
    created_at: action.created_at,
  }]
}
