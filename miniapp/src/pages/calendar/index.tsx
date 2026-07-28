import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Text, View } from '@tarojs/components'
import { getOrCreateConversationId } from '@/services/conversations'
import { ensureSession } from '@/services/session'
import { workspaceOperation } from '@/services/workspace'
import { localeFor, readLanguage, translate, type Language } from '@/i18n'
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
  const [language, setLanguage] = useState<Language>(readLanguage())

  const load = () => {
    setLoading(true)
    void ensureSession()
      .then((session) => workspaceOperation(getOrCreateConversationId(session), 'get'))
      .then((result) => setSchedules((result.schedules || []) as Schedule[]))
      .catch((reason) => Taro.showToast({ title: String((reason as Error)?.message || translate('readFailed')), icon: 'none' }))
      .finally(() => setLoading(false))
  }
  useDidShow(() => {
    const nextLanguage = readLanguage()
    setLanguage(nextLanguage)
    void Taro.setNavigationBarTitle({ title: translate('navCalendar', {}, nextLanguage) })
    load()
  })

  return <View className='calendar-page'>
    {loading ? <Text className='calendar-state'>{translate('loadingCalendar', {}, language)}</Text> : null}
    {!loading && !schedules.length ? <Text className='calendar-state'>{translate('noCalendar', {}, language)}</Text> : null}
    {schedules.map((schedule) => {
      const start = new Date(Number(schedule.start_time || 0) * 1000)
      const end = new Date(start.getTime() + Number(schedule.duration_minutes || 0) * 60_000)
      return <View className='schedule-row' key={schedule.id || `${schedule.title}-${schedule.start_time}`}>
        <View className='schedule-time'>
          <Text>{start.toLocaleDateString(localeFor(language), { month: 'numeric', day: 'numeric' })}</Text>
          <Text>{start.toLocaleTimeString(localeFor(language), { hour: '2-digit', minute: '2-digit' })}</Text>
        </View>
        <View className='schedule-copy'>
          <Text className='schedule-title'>{schedule.title || translate('unnamedSchedule', {}, language)}</Text>
          <Text className='schedule-detail'>{translate('untilTime', {
            time: end.toLocaleTimeString(localeFor(language), { hour: '2-digit', minute: '2-digit' }),
          }, language)}{schedule.location ? ` · ${schedule.location}` : ''}</Text>
          {schedule.description ? <Text className='schedule-description'>{schedule.description}</Text> : null}
        </View>
      </View>
    })}
    <View className='calendar-hint'>{translate('calendarHint', {}, language)}</View>
  </View>
}
