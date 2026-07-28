import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Text, View } from '@tarojs/components'
import { getOrCreateConversationId } from '@/services/conversations'
import {
  activeProactiveNotifications,
  proactiveOperation,
  type ProactiveNotification,
} from '@/services/proactive'
import { ensureSession } from '@/services/session'
import './index.scss'

const PENDING_PROMPT_KEY = 'floris.miniapp.pending-proactive-prompt.v1'

export default function ProactivePage() {
  const [conversationId, setConversationId] = useState('')
  const [notifications, setNotifications] = useState<ProactiveNotification[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')

  const load = async (refresh = false) => {
    setLoading(true)
    try {
      const session = await ensureSession()
      const id = getOrCreateConversationId(session)
      setConversationId(id)
      const state = await proactiveOperation(id, refresh ? 'refresh' : 'get')
      setNotifications(activeProactiveNotifications(state.notifications || []))
    } catch (reason) {
      void Taro.showToast({ title: String((reason as Error)?.message || '提醒读取失败'), icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  useDidShow(() => { void load(false) })

  const mutate = async (
    item: ProactiveNotification,
    operation: 'mark_read' | 'snooze' | 'dismiss',
  ) => {
    if (!conversationId || busy) return
    setBusy(item.id)
    try {
      const state = await proactiveOperation(conversationId, operation, {
        notification_id: item.id,
        ...(operation === 'snooze'
          ? { until: Math.floor(Date.now() / 1000) + 3600 }
          : {}),
      })
      setNotifications(activeProactiveNotifications(state.notifications || []))
      if (operation === 'mark_read' && item.action_prompt) {
        Taro.setStorageSync(PENDING_PROMPT_KEY, item.action_prompt)
        await Taro.navigateBack()
      }
    } catch (reason) {
      void Taro.showToast({ title: String((reason as Error)?.message || '操作失败'), icon: 'none' })
    } finally {
      setBusy('')
    }
  }

  return <View className='proactive-page'>
    <View className='proactive-toolbar'>
      <Text>Floris 为你留意到</Text>
      <Button loading={loading} disabled={Boolean(busy)} onClick={() => void load(true)}>刷新</Button>
    </View>
    {!loading && !notifications.length
      ? <Text className='proactive-empty'>目前没有需要打扰你的事。有可靠的新机会时，Floris 会在这里提醒。</Text>
      : null}
    {notifications.map((item) => <View className={`proactive-item priority-${item.priority || 'normal'}`} key={item.id}>
      <Text className='proactive-title'>{item.title || '一条温柔提醒'}</Text>
      <Text className='proactive-body'>{item.body || ''}</Text>
      {item.status === 'snoozed' && item.snoozed_until
        ? <Text className='proactive-time'>稍后提醒：{new Date(item.snoozed_until * 1000).toLocaleString()}</Text>
        : null}
      <View className='proactive-actions'>
        <Button className='proactive-handle' disabled={Boolean(busy)} onClick={() => void mutate(item, 'mark_read')}>处理建议</Button>
        <Button className='proactive-later' disabled={Boolean(busy)} onClick={() => void mutate(item, 'snooze')}>一小时后</Button>
        <Button className='proactive-ignore' disabled={Boolean(busy)} onClick={() => void mutate(item, 'dismiss')}>忽略</Button>
      </View>
    </View>)}
  </View>
}
