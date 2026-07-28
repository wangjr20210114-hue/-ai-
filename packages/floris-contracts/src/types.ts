export type ClarificationFieldType =
  | 'single' | 'multi' | 'boolean' | 'text' | 'date' | 'time' | 'datetime'

export interface ClarificationField {
  id: string
  label: string
  type: ClarificationFieldType
  options?: string[]
  option_values?: Record<string, string>
  required?: boolean
  placeholder?: string
}

export interface ClarificationPrompt {
  id: string
  title: string
  prompt: string
  fields: ClarificationField[]
}

export interface SearchMedia {
  id?: string
  kind?: string
  url: string
  caption?: string
  alt?: string
  source_url?: string
  source_title?: string
}

export interface SearchResultItem {
  id?: string
  title: string
  url: string
  snippet?: string
  source?: string
}

export interface SearchMeta {
  results?: SearchResultItem[]
  media?: SearchMedia[]
  media_pending?: boolean
}

export interface PaperInfo {
  title: string
  arxiv_id?: string
  authors?: string
  year?: number
  abstract_zh?: string
  key_contribution?: string
  citations?: string
  arxiv_url?: string
  pdf_url?: string
  source_url?: string
}

export interface WorkspaceAction {
  id: string
  kind: 'map_recommendation' | 'calendar_changes' | 'meeting_create' | 'image_generate'
  status: string
  version: number
  payload: Record<string, unknown>
  result?: Record<string, unknown> | null
}

export interface ChatMessage {
  id: string
  role: 'user' | 'ai'
  content: string
  ts: number
  streaming?: boolean
  failed?: boolean
  followUps?: string[]
  searchResults?: SearchMeta
  papers?: PaperInfo[]
  workspaceActions?: WorkspaceAction[]
  clarification?: ClarificationPrompt
  clarificationAnswered?: boolean
}

export interface MiniappSession {
  token: string
  expiresAt: number
  userId: string
  conversationPrefix: string
}

export interface FlorisStreamEvent {
  type: string
  content?: string
  message?: string
  follow_ups?: string[]
  search_results?: SearchMeta
  payload?: Record<string, unknown>
  name?: string
  [key: string]: unknown
}
