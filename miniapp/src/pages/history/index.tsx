import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Text, View } from '@tarojs/components'
import {
  listConversations,
  setActiveConversationId,
  type ConversationSummary,
} from '@/services/conversations'
import { localeFor, readLanguage, translate, type Language } from '@/i18n'
import './index.scss'

export default function HistoryPage() {
  const [items, setItems] = useState<ConversationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [language, setLanguage] = useState<Language>(readLanguage())

  const load = () => {
    setLoading(true)
    setError('')
    void listConversations()
      .then(setItems)
      .catch((reason) => setError(String((reason as Error)?.message || reason)))
      .finally(() => setLoading(false))
  }

  useDidShow(() => {
    const nextLanguage = readLanguage()
    setLanguage(nextLanguage)
    void Taro.setNavigationBarTitle({ title: translate('navHistory', {}, nextLanguage) })
    load()
  })

  const open = async (id: string) => {
    setActiveConversationId(id)
    await Taro.reLaunch({ url: '/pages/index/index' })
  }

  return <View className='history-page'>
    {loading ? <Text className='page-state'>{translate('loadingHistory', {}, language)}</Text> : null}
    {error ? <View className='page-state'><Text>{error}</Text><Button onClick={load}>{translate('retry', {}, language)}</Button></View> : null}
    {!loading && !error && !items.length ? <Text className='page-state'>{translate('noHistory', {}, language)}</Text> : null}
    {items.map((item) => <View className='conversation-item' key={item.id} onClick={() => void open(item.id)}>
      <View className='conversation-main'>
        <Text className='conversation-title'>{item.title}</Text>
        <Text className='conversation-time'>{new Date(item.updatedAt).toLocaleString(localeFor(language))}</Text>
      </View>
      <Text className='conversation-count'>{translate('messageCount', { count: item.messageCount }, language)}</Text>
    </View>)}
  </View>
}
