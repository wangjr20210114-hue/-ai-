import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Text, View } from '@tarojs/components'
import { apiRequest } from '@/services/request'
import { openMakersDocument } from '@/services/files'
import './index.scss'

type ReadingItem = {
  id: string
  title?: string
  filename?: string
  storage_key?: string
  is_paper?: boolean
  created_at?: number
}

export default function LibraryPage() {
  const [items, setItems] = useState<ReadingItem[]>([])
  const [loading, setLoading] = useState(true)
  const [opening, setOpening] = useState('')

  const load = () => {
    setLoading(true)
    void apiRequest<{ items?: ReadingItem[] }>('/library')
      .then((result) => setItems(result.items || []))
      .catch((reason) => Taro.showToast({ title: String((reason as Error)?.message || '读取失败'), icon: 'none' }))
      .finally(() => setLoading(false))
  }
  useDidShow(load)

  const open = async (item: ReadingItem) => {
    if (!item.storage_key || opening) return
    setOpening(item.id)
    try {
      await openMakersDocument(item.storage_key)
      await apiRequest('/library', {
        method: 'POST',
        data: { operation: 'touch', id: item.id },
      }).catch(() => undefined)
    } catch (reason) {
      void Taro.showToast({ title: String((reason as Error)?.message || '打开失败'), icon: 'none' })
    } finally {
      setOpening('')
    }
  }

  return <View className='library-page'>
    {loading ? <Text className='library-state'>正在读取“我的阅读”…</Text> : null}
    {!loading && !items.length ? <View className='library-state'>
      <Text>还没有保存的论文或 PDF</Text>
      <Text>回到对话页，点击输入框左侧的“＋”上传。</Text>
    </View> : null}
    {items.map((item) => <View className='library-item' key={item.id}>
      <View className='file-badge'>PDF</View>
      <View className='file-copy'>
        <Text className='file-title'>{item.title || item.filename || 'PDF 文档'}</Text>
        <Text className='file-kind'>{item.is_paper ? '论文' : 'PDF'} · 微信原生预览</Text>
      </View>
      <View className='file-actions'>
        <Button className='assist-button' onClick={() => {
          Taro.setStorageSync('floris.miniapp.reader-file.v1', item.storage_key || '')
          void Taro.navigateTo({ url: '/pages/reader/index' })
        }}>助读</Button>
        <Button className='open-button' loading={opening === item.id} onClick={() => void open(item)}>打开</Button>
      </View>
    </View>)}
  </View>
}
