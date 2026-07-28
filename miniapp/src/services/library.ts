import { apiRequest } from './request'

export interface ReadingFolder {
  id: string
  name: string
  automatic?: boolean
  created_at?: number
}

export interface ReadingItem {
  id: string
  title?: string
  filename?: string
  storage_key?: string
  is_paper?: boolean
  created_at?: number
  folder_id?: string
}

export interface ReadingLibrary {
  items: ReadingItem[]
  folders: ReadingFolder[]
  settings: { auto_organize: boolean }
}

export async function getReadingLibrary(): Promise<ReadingLibrary> {
  const data = await apiRequest<{
    items?: ReadingItem[]
    folders?: ReadingFolder[]
    settings?: { auto_organize?: boolean }
  }>('/library')
  return {
    items: data.items || [],
    folders: data.folders || [],
    settings: { auto_organize: data.settings?.auto_organize !== false },
  }
}

export function updateReadingSetting(autoOrganize: boolean): Promise<unknown> {
  return apiRequest('/library', {
    method: 'POST',
    data: { operation: 'settings', auto_organize: autoOrganize },
  })
}

export function createReadingFolder(name: string): Promise<unknown> {
  return apiRequest('/library', {
    method: 'POST',
    data: { operation: 'create_folder', name },
  })
}

export function renameReadingFolder(folderId: string, name: string): Promise<unknown> {
  return apiRequest('/library', {
    method: 'POST',
    data: { operation: 'rename_folder', folder_id: folderId, name },
  })
}

export function moveReadingItem(itemId: string, folderId: string): Promise<unknown> {
  return apiRequest('/library', {
    method: 'POST',
    data: { operation: 'move_item', item_id: itemId, folder_id: folderId },
  })
}

export function deleteReadingItem(itemId: string): Promise<unknown> {
  return apiRequest(`/library?id=${encodeURIComponent(itemId)}`, { method: 'DELETE' })
}

export function deleteReadingFolder(folderId: string): Promise<unknown> {
  return apiRequest(`/library?folder_id=${encodeURIComponent(folderId)}`, { method: 'DELETE' })
}
