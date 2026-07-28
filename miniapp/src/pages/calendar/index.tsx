import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Text, View } from '@tarojs/components'
import { getOrCreateConversationId } from '@/services/conversations'
import { ensureSession } from '@/services/session'
import { workspaceOperation } from '@/services/workspace'
import './index.scss'

type Schedule = {
  id?: string
  title?: string
  start_time?: number
  duration_minutes?: number
  location?: string
  address?: string
  description?: string
  category?: string
}

export default function CalendarPage() {
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    void ensureSession()
      .then((session) => workspaceOperation(getOrCreateConversationId(session), 'get'))
      .then((result) => setSchedules((result.schedules || []) as Schedule[]))
      .catch((reason) => Taro.showToast({ title: String((reason as Error)?.message || '读取失败'), icon: 'none' }))
      .finally(() => setLoading(false))
  }
  useDidShow(load)

  return <View className='calendar-page'>
    {loading ? <Text className='calendar-state'>正在读取日程…</Text> : null}
    {!loading && !schedules.length ? <Text className='calendar-state'>还没有日程。你可以直接在对话里请 Floris 安排。</Text> : null}
    {schedules.map((schedule) => {
      const start = new Date(Number(schedule.start_time || 0) * 1000)
      const end = new Date(start.getTime() + Number(schedule.duration_minutes || 0) * 60_000)
      return <View className='schedule-row' key={schedule.id || `${schedule.title}-${schedule.start_time}`}>
        <View className='schedule-time'>
          <Text>{start.toLocaleDateString().slice(5)}</Text>
          <Text>{start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</Text>
        </View>
        <View className='schedule-copy'>
          <Text className='schedule-title'>{schedule.title || '未命名日程'}</Text>
          <Text className='schedule-detail'>至 {end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}{schedule.location ? ` · ${schedule.location}` : ''}</Text>
          {schedule.description ? <Text className='schedule-description'>{schedule.description}</Text> : null}
        </View>
      </View>
    })}
    <View className='calendar-hint'>新增、编辑、删除和冲突检查继续通过对话完成，由现有 Calendar Skill 生成确认卡。</View>
  </View>
}
