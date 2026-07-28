import { useMemo, useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Input, Picker, Text, Textarea, View } from '@tarojs/components'
import { capabilityEnabled, type SkillCapabilityDefinition } from '@floris/contracts'
import {
  isPastCalendarDay,
  localDateValue,
  localTimestamp,
  localTimeValue,
  schedulesForDay,
  todayValue,
  type CalendarSchedule,
} from '@/services/calendar'
import { getOrCreateConversationId } from '@/services/conversations'
import { searchVerifiedPlaces, type VerifiedPlace } from '@/services/places'
import { apiRequest } from '@/services/request'
import { ensureSession } from '@/services/session'
import { updateNativeTabBar } from '@/services/tabbar'
import { workspaceOperation } from '@/services/workspace'
import { localeFor, readLanguage, translate, type Language } from '@/i18n'
import './index.scss'

type CalendarForm = {
  id: string
  title: string
  date: string
  start: string
  end: string
  description: string
  category: string
  locationQuery: string
  selectedPlace?: VerifiedPlace
  placeTouched: boolean
}

function roundedStart(date: string): Date {
  const now = new Date()
  const value = new Date(
    Number(date.slice(0, 4)),
    Number(date.slice(5, 7)) - 1,
    Number(date.slice(8, 10)),
    date === todayValue(now) ? now.getHours() + 1 : 9,
    0,
  )
  return value
}

function formForSchedule(schedule: CalendarSchedule | undefined, date: string): CalendarForm {
  if (!schedule) {
    const start = roundedStart(date)
    const end = new Date(start.getTime() + 60 * 60_000)
    return {
      id: '',
      title: '',
      date,
      start: localTimeValue(start),
      end: localTimeValue(end),
      description: '',
      category: 'other',
      locationQuery: '',
      placeTouched: false,
    }
  }
  const start = new Date(Number(schedule.start_time || 0) * 1000)
  const end = new Date(start.getTime() + Number(schedule.duration_minutes || 60) * 60_000)
  const rawPlace = schedule.extra?.place
  const selectedPlace = rawPlace
    && typeof rawPlace.place_id === 'string'
    && typeof rawPlace.name === 'string'
    && typeof rawPlace.latitude === 'number'
    && typeof rawPlace.longitude === 'number'
    ? rawPlace as unknown as VerifiedPlace
    : undefined
  return {
    id: String(schedule.id || ''),
    title: String(schedule.title || ''),
    date: localDateValue(start),
    start: localTimeValue(start),
    end: localTimeValue(end),
    description: String(schedule.description || ''),
    category: String(schedule.category || 'other'),
    locationQuery: String(schedule.location || selectedPlace?.name || ''),
    selectedPlace,
    placeTouched: false,
  }
}

export default function CalendarPage() {
  const [schedules, setSchedules] = useState<CalendarSchedule[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [language, setLanguage] = useState<Language>(readLanguage())
  const [conversationId, setConversationId] = useState('')
  const [selectedDate, setSelectedDate] = useState(todayValue())
  const [form, setForm] = useState<CalendarForm | null>(null)
  const [places, setPlaces] = useState<VerifiedPlace[]>([])
  const [searchingPlaces, setSearchingPlaces] = useState(false)
  const [calendarEnabled, setCalendarEnabled] = useState(true)
  const [mapsEnabled, setMapsEnabled] = useState(true)

  const load = () => {
    setLoading(true)
    void ensureSession()
      .then(async (session) => {
        const id = getOrCreateConversationId(session)
        setConversationId(id)
        const [workspace, intelligence] = await Promise.all([
          workspaceOperation(id, 'get'),
          apiRequest<{
            skill_preferences?: Record<string, boolean>
            skill_catalog?: SkillCapabilityDefinition[]
          }>('/intelligence', {
            method: 'POST',
            conversationId: id,
            data: { operation: 'get' },
          }).catch(() => ({
            skill_preferences: {},
            skill_catalog: [],
          })),
        ])
        const catalog = intelligence.skill_catalog || []
        const preferences = intelligence.skill_preferences || {}
        setCalendarEnabled(capabilityEnabled(catalog, preferences, 'calendar_changes'))
        setMapsEnabled(capabilityEnabled(catalog, preferences, 'places'))
        setSchedules((workspace.schedules || []) as CalendarSchedule[])
      })
      .catch((reason) => Taro.showToast({
        title: String((reason as Error)?.message || translate('readFailed')),
        icon: 'none',
      }))
      .finally(() => setLoading(false))
  }

  useDidShow(() => {
    const nextLanguage = readLanguage()
    setLanguage(nextLanguage)
    void Taro.setNavigationBarTitle({ title: translate('navCalendar', {}, nextLanguage) })
    void updateNativeTabBar(nextLanguage)
    load()
  })

  const daySchedules = useMemo(
    () => schedulesForDay(schedules, selectedDate),
    [schedules, selectedDate],
  )
  const readOnly = isPastCalendarDay(selectedDate)

  const openEditor = (schedule?: CalendarSchedule) => {
    if (!calendarEnabled || readOnly) return
    const next = formForSchedule(schedule, selectedDate)
    setForm(next)
    setPlaces([])
  }

  const searchPlaces = async () => {
    if (!form || !conversationId || !form.locationQuery.trim() || searchingPlaces) return
    setSearchingPlaces(true)
    try {
      const result = await searchVerifiedPlaces(conversationId, form.locationQuery.trim())
      setPlaces(result)
      if (!result.length) {
        void Taro.showToast({ title: translate('noPlaceFound', {}, language), icon: 'none' })
      }
    } catch (reason) {
      void Taro.showToast({
        title: String((reason as Error)?.message || translate('operationFailed', {}, language)),
        icon: 'none',
      })
    } finally {
      setSearchingPlaces(false)
    }
  }

  const save = async () => {
    if (!form || !conversationId || saving) return
    if (!form.title.trim()) {
      void Taro.showToast({ title: translate('invalidEventTitle', {}, language), icon: 'none' })
      return
    }
    const startTime = localTimestamp(form.date, form.start)
    const endTime = localTimestamp(form.date, form.end)
    if (endTime <= startTime) {
      void Taro.showToast({ title: translate('invalidEventTime', {}, language), icon: 'none' })
      return
    }
    const event: Record<string, unknown> = {
      title: form.title.trim(),
      start_time: startTime,
      duration_minutes: Math.max(1, Math.round((endTime - startTime) / 60)),
      description: form.description.trim(),
      category: form.category || 'other',
    }
    if (!form.id || form.placeTouched) {
      event.place = form.selectedPlace || null
      event.location = form.selectedPlace?.address || form.selectedPlace?.name || ''
    }
    setSaving(true)
    try {
      const result = await workspaceOperation(conversationId, 'direct_calendar_changes', {
        changes: [{
          operation: form.id ? 'update' : 'create',
          ...(form.id ? { schedule_id: form.id } : {}),
          event,
        }],
      })
      setSchedules((result.schedules || []) as CalendarSchedule[])
      setSelectedDate(form.date)
      setForm(null)
      setPlaces([])
      void Taro.showToast({ title: translate('eventSaved', {}, language), icon: 'success' })
    } catch (reason) {
      void Taro.showToast({
        title: String((reason as Error)?.message || translate('saveFailed', {}, language)),
        icon: 'none',
      })
    } finally {
      setSaving(false)
    }
  }

  const remove = async (schedule: CalendarSchedule) => {
    if (!schedule.id || !conversationId || saving || readOnly) return
    const answer = await Taro.showModal({
      title: translate('deleteEventTitle', {}, language),
      content: translate('deleteEventBody', {}, language),
      confirmText: translate('delete', {}, language),
      cancelText: translate('cancel', {}, language),
      confirmColor: '#c95147',
    })
    if (!answer.confirm) return
    setSaving(true)
    try {
      const result = await workspaceOperation(conversationId, 'direct_calendar_changes', {
        changes: [{ operation: 'delete', schedule_id: schedule.id }],
      })
      setSchedules((result.schedules || []) as CalendarSchedule[])
      if (form?.id === schedule.id) setForm(null)
      void Taro.showToast({ title: translate('eventDeleted', {}, language), icon: 'success' })
    } catch (reason) {
      void Taro.showToast({
        title: String((reason as Error)?.message || translate('operationFailed', {}, language)),
        icon: 'none',
      })
    } finally {
      setSaving(false)
    }
  }

  return <View className='calendar-page'>
    <View className='calendar-toolbar'>
      <Picker mode='date' value={selectedDate} onChange={(event) => {
        const value = String(event.detail.value)
        setSelectedDate(value)
        setForm(null)
        setPlaces([])
      }}>
        <View className='calendar-date'>{selectedDate} 〉</View>
      </Picker>
      <Button
        className='calendar-add'
        disabled={loading || readOnly || !calendarEnabled}
        onClick={() => openEditor()}
      >＋ {translate('calendarAdd', {}, language)}</Button>
    </View>

    {!calendarEnabled ? <View className='calendar-skill-off'>
      <Text>{translate('calendarSkillOff', {}, language)}</Text>
      <Button onClick={() => Taro.switchTab({ url: '/pages/settings/index' })}>
        {translate('navSettings', {}, language)}
      </Button>
    </View> : null}

    {readOnly ? <Text className='calendar-readonly'>{translate('calendarReadOnly', {}, language)}</Text> : null}
    {loading ? <Text className='calendar-state'>{translate('loadingCalendar', {}, language)}</Text> : null}
    {!loading && !daySchedules.length
      ? <Text className='calendar-state calendar-state-empty'>{translate('noCalendar', {}, language)}</Text>
      : null}

    {daySchedules.map((schedule) => {
      const start = new Date(Number(schedule.start_time || 0) * 1000)
      const end = new Date(start.getTime() + Number(schedule.duration_minutes || 0) * 60_000)
      return <View className='schedule-row' key={schedule.id || `${schedule.title}-${schedule.start_time}`}>
        <View className='schedule-time'>
          <Text>{start.toLocaleTimeString(localeFor(language), { hour: '2-digit', minute: '2-digit' })}</Text>
          <Text>{translate('untilTime', {
            time: end.toLocaleTimeString(localeFor(language), { hour: '2-digit', minute: '2-digit' }),
          }, language)}</Text>
        </View>
        <View className='schedule-copy'>
          <Text className='schedule-title'>{schedule.title || translate('unnamedSchedule', {}, language)}</Text>
          {schedule.location ? <Text className='schedule-detail'>⌖ {schedule.location}</Text> : null}
          {schedule.description ? <Text className='schedule-description'>{schedule.description}</Text> : null}
          {!readOnly && calendarEnabled ? <View className='schedule-actions'>
            <Button size='mini' disabled={saving} onClick={() => openEditor(schedule)}>
              {translate('edit', {}, language)}
            </Button>
            <Button size='mini' disabled={saving} onClick={() => void remove(schedule)}>
              {translate('delete', {}, language)}
            </Button>
          </View> : null}
        </View>
      </View>
    })}

    {form ? <View className='calendar-editor'>
      <View className='editor-heading'>
        <Text>{translate(form.id ? 'calendarEdit' : 'calendarAdd', {}, language)}</Text>
        <Button size='mini' onClick={() => setForm(null)}>×</Button>
      </View>
      <Text className='field-label'>{translate('eventTitle', {}, language)}</Text>
      <Input
        className='editor-input'
        value={form.title}
        maxlength={120}
        placeholder={translate('eventTitlePlaceholder', {}, language)}
        onInput={(event) => setForm({ ...form, title: event.detail.value })}
      />
      <View className='date-time-grid'>
        <View>
          <Text className='field-label'>{translate('eventDate', {}, language)}</Text>
          <Picker mode='date' value={form.date} start={todayValue()} onChange={(event) => {
            setForm({ ...form, date: String(event.detail.value) })
          }}>
            <View className='editor-picker'>{form.date} 〉</View>
          </Picker>
        </View>
        <View>
          <Text className='field-label'>{translate('eventStart', {}, language)}</Text>
          <Picker mode='time' value={form.start} onChange={(event) => {
            setForm({ ...form, start: String(event.detail.value) })
          }}>
            <View className='editor-picker'>{form.start} 〉</View>
          </Picker>
        </View>
        <View>
          <Text className='field-label'>{translate('eventEnd', {}, language)}</Text>
          <Picker mode='time' value={form.end} onChange={(event) => {
            setForm({ ...form, end: String(event.detail.value) })
          }}>
            <View className='editor-picker'>{form.end} 〉</View>
          </Picker>
        </View>
      </View>
      <Text className='field-label'>{translate('eventNotes', {}, language)}</Text>
      <Textarea
        className='editor-textarea'
        value={form.description}
        maxlength={1000}
        placeholder={translate('eventNotesPlaceholder', {}, language)}
        onInput={(event) => setForm({ ...form, description: event.detail.value })}
      />
      {mapsEnabled ? <>
        <Text className='field-label'>{translate('eventLocation', {}, language)}</Text>
        <View className='place-search'>
          <Input
            className='editor-input'
            value={form.locationQuery}
            placeholder={translate('eventLocationPlaceholder', {}, language)}
            onInput={(event) => setForm({ ...form, locationQuery: event.detail.value })}
          />
          <Button loading={searchingPlaces} disabled={!form.locationQuery.trim() || searchingPlaces}
            onClick={() => void searchPlaces()}>{translate('searchPlace', {}, language)}</Button>
        </View>
        {form.selectedPlace ? <View className='selected-place'>
          <Text>{translate('selectedPlace', { name: form.selectedPlace.name }, language)}</Text>
          <Button size='mini' onClick={() => setForm({
            ...form,
            selectedPlace: undefined,
            locationQuery: '',
            placeTouched: true,
          })}>{translate('clearLocation', {}, language)}</Button>
        </View> : null}
        {places.length ? <View className='place-results'>
          {places.map((place) => <View
            className={`place-option ${form.selectedPlace?.place_id === place.place_id ? 'is-selected' : ''}`}
            key={place.place_id}
            hoverClass='floris-card-press'
            hoverStayTime={80}
            onClick={() => setForm({
              ...form,
              selectedPlace: place,
              locationQuery: place.name,
              placeTouched: true,
            })}
          >
            <Text className='place-name'>{place.name}</Text>
            <Text className='place-address'>{place.address || ''}</Text>
          </View>)}
        </View> : null}
      </> : null}
      <View className='editor-actions'>
        <Button disabled={saving} onClick={() => setForm(null)}>{translate('cancel', {}, language)}</Button>
        <Button className='primary' loading={saving} disabled={saving} onClick={() => void save()}>
          {translate('saveEvent', {}, language)}
        </Button>
      </View>
    </View> : null}
  </View>
}
