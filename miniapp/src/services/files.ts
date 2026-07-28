import Taro from '@tarojs/taro'
import { translate } from '@/i18n'
import { apiUrl } from './config'
import { apiRequest } from './request'
import { ensureSession } from './session'

export interface MiniappFile {
  storageKey: string
  name: string
  mimeType: string
  contentUrl: string
}

function readFile(path: string, encoding?: 'base64'): Promise<string | ArrayBuffer> {
  return new Promise((resolve, reject) => {
    Taro.getFileSystemManager().readFile({
      filePath: path,
      ...(encoding ? { encoding } : {}),
      success: (result) => resolve(result.data),
      fail: reject,
    })
  })
}

export async function imageDataUrl(path: string): Promise<string> {
  const compressed = await Taro.compressImage({ src: path, quality: 76 }).catch(() => ({ tempFilePath: path }))
  const base64 = await readFile(compressed.tempFilePath, 'base64')
  const extension = compressed.tempFilePath.toLowerCase().endsWith('.png') ? 'png' : 'jpeg'
  const value = `data:image/${extension};base64,${String(base64)}`
  if (value.length > 1_800_000) throw new Error(translate('imageTooLarge'))
  return value
}

export async function uploadToMakers(
  conversationId: string,
  path: string,
  name: string,
  mimeType = 'application/pdf',
  size?: number,
): Promise<MiniappFile> {
  const info = size ? null : await Taro.getFileInfo({ filePath: path })
  const fileSize = size || Number((info as { size?: number } | null)?.size || 0)
  const signed = await apiRequest<{
    url: string
    key: string
    content_url?: string
  }>('/files', {
    method: 'POST',
    data: {
      conversation_id: conversationId,
      name,
      content_type: mimeType,
      size: fileSize,
    },
  })
  const bytes = await readFile(path)
  const upload = await Taro.request({
    url: signed.url,
    method: 'PUT',
    header: { 'content-type': mimeType },
    data: bytes,
    responseType: 'text',
    timeout: 120_000,
  })
  if (upload.statusCode < 200 || upload.statusCode >= 300) throw new Error(translate('fileUploadFailed'))
  return {
    storageKey: signed.key,
    name,
    mimeType,
    contentUrl: signed.content_url || `/files?key=${encodeURIComponent(signed.key)}`,
  }
}

export async function addPdfToReading(file: MiniappFile): Promise<void> {
  await apiRequest('/library', {
    method: 'POST',
    data: {
      operation: 'register',
      storage_key: file.storageKey,
      filename: file.name,
      title: file.name.replace(/\.pdf$/i, ''),
      mime_type: file.mimeType,
      is_paper: false,
      page_count: 0,
      preview: translate('miniappPdfPreview'),
    },
  })
}

export async function openMakersDocument(storageKey: string): Promise<void> {
  const session = await ensureSession()
  const download = await Taro.downloadFile({
    url: apiUrl(`/files?key=${encodeURIComponent(storageKey)}`),
    header: {
      Authorization: `Bearer ${session.token}`,
      'x-floris-client': 'wechat-miniapp',
    },
  })
  if (download.statusCode !== 200) throw new Error(translate('documentDownloadFailed'))
  await Taro.openDocument({
    filePath: download.tempFilePath,
    fileType: 'pdf',
    showMenu: true,
  })
}
