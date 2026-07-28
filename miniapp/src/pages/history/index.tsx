import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Text, View } from '@tarojs/components'
import {
  listConversations,
  setActiveConversationId,
  type ConversationSummary,
} from '@/services/conversations'
import './index.scss'

export default function HistoryPage() {
  const [items, setItems] = useState<ConversationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = () => {
    setLoading(true)
    setError('')
    void listConversations()
      .then(setItems)
      .catch((reason) => setError(String((reason as Error)?.message || reason)))
      .finally(() => setLoading(false))
  }

  useDidShow(load)

  const open = async (id: string) => {
    setActiveConversationId(id)
    await Taro.reLaunch({ url: '/pages/index/index' })
  }

  return <View className='history-page'>
    {loading ? <Text className='page-state'>正在读取历史对话…</Text> : null}
    {error ? <View className='page-state'><Text>{error}</Text><Button onClick={load}>重试</Button></View> : null}
    {!loading && !error && !items.length ? <Text className='page-state'>还没有历史对话</Text> : null}
    {items.map((item) => <View className='conversation-item' key={item.id} onClick={() => void open(item.id)}>
      <View className='conversation-main'>
        <Text className='conversation-title'>{item.title}</Text>
        <Text className='conversation-time'>{new Date(item.updatedAt).toLocaleString()}</Text>
      </View>
      <Text className='conversation-count'>{item.messageCount} 条</Text>
    </View>)}
  </View>
}
