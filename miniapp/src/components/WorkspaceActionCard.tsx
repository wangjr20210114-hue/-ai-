import { useEffect, useMemo, useState } from 'react'
import Taro from '@tarojs/taro'
import {
  Button,
  Checkbox,
  CheckboxGroup,
  Input,
  Label,
  Picker,
  Swiper,
  SwiperItem,
  Text,
  View,
} from '@tarojs/components'
import { imageVersionsFrom, type WorkspaceAction } from '@floris/contracts'
import MakersImage from './MakersImage'

export type WorkspaceOperation =
  | 'activate_map'
  | 'update_meeting_action'
  | 'confirm_action'
  | 'cancel_action'

interface Props {
  action: WorkspaceAction
  busy?: boolean
  onExecute: (
    action: WorkspaceAction,
    operation: WorkspaceOperation,
    input?: Record<string, unknown>,
  ) => void
}

const actionName = (kind: WorkspaceAction['kind']) => ({
  map_recommendation: '地点与路线',
  calendar_changes: '日程变更',
  meeting_create: '腾讯会议',
  image_generate: '图片创作',
}[kind])

const arrayOfRecords = (value: unknown): Array<Record<string, unknown>> => (
  Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
    : []
)

const arrayOfStrings = (value: unknown): string[] => (
  Array.isArray(value) ? value.map(String).filter(Boolean) : []
)

function localDateTime(value: unknown): { date: string; time: string } {
  const date = new Date(String(value || ''))
  if (!Number.isFinite(date.getTime())) return { date: '', time: '' }
  const pad = (part: number) => String(part).padStart(2, '0')
  return {
    date: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    time: `${pad(date.getHours())}:${pad(date.getMinutes())}`,
  }
}

function isoFromParts(date: string, time: string): string {
  if (!date || !time) return ''
  const parsed = new Date(`${date}T${time}:00`)
  return Number.isFinite(parsed.getTime()) ? parsed.toISOString() : ''
}

function formatScheduleTime(value: unknown): string {
  const number = Number(value || 0)
  if (!number) return '时间待确认'
  return new Date(number * 1000).toLocaleString()
}

function CalendarDetails({ action }: { action: WorkspaceAction }) {
  const changes = arrayOfRecords(action.payload.changes)
  const warnings = arrayOfStrings(action.payload.warnings)
  return <>
    {changes.map((change, index) => {
      const operation = String(change.operation || 'create')
      const event = (
        change.event && typeof change.event === 'object'
          ? change.event as Record<string, unknown>
          : {}
      )
      const place = (
        event.place && typeof event.place === 'object'
          ? event.place as Record<string, unknown>
          : {}
      )
      const operationLabel = operation === 'delete' ? '删除' : operation === 'update' ? '修改' : '新增'
      return <View className='action-detail-row' key={`${operation}-${change.schedule_id || index}`}>
        <Text className={`action-operation operation-${operation}`}>{operationLabel}</Text>
        <View className='action-detail-copy'>
          <Text className='action-detail-title'>{String(event.title || change.title || '日程')}</Text>
          {operation !== 'delete'
            ? <Text className='action-detail-meta'>{formatScheduleTime(event.start_time)}
              {event.duration_minutes ? ` · ${Number(event.duration_minutes)} 分钟` : ''}
            </Text>
            : null}
          {event.location || place.name || place.address
            ? <Text className='action-detail-meta'>{String(place.name || event.location || place.address)}</Text>
            : null}
        </View>
      </View>
    })}
    {warnings.map((warning) => <Text className='action-warning' key={warning}>请留意：{warning}</Text>)}
  </>
}

function MeetingDetails({
  action,
  busy,
  onExecute,
}: {
  action: WorkspaceAction
  busy: boolean
  onExecute: Props['onExecute']
}) {
  const initialStart = useMemo(() => localDateTime(action.payload.start_time), [
    action.payload.start_time,
  ])
  const initialEnd = useMemo(() => localDateTime(action.payload.end_time), [
    action.payload.end_time,
  ])
  const [subject, setSubject] = useState(String(action.payload.subject || '腾讯会议'))
  const [startDate, setStartDate] = useState(initialStart.date)
  const [startTime, setStartTime] = useState(initialStart.time)
  const [endDate, setEndDate] = useState(initialEnd.date)
  const [endTime, setEndTime] = useState(initialEnd.time)
  const [acceptedWarnings, setAcceptedWarnings] = useState<string[]>([])
  const warnings = arrayOfStrings(action.payload.warnings)
  const errors = arrayOfStrings(action.payload.validation_errors)
  const missing = arrayOfStrings(action.payload.missing_fields)
  const result = action.result || {}

  useEffect(() => {
    const nextStart = localDateTime(action.payload.start_time)
    const nextEnd = localDateTime(action.payload.end_time)
    setSubject(String(action.payload.subject || '腾讯会议'))
    setStartDate(nextStart.date)
    setStartTime(nextStart.time)
    setEndDate(nextEnd.date)
    setEndTime(nextEnd.time)
    setAcceptedWarnings([])
  }, [
    action.id,
    action.version,
    action.payload.subject,
    action.payload.start_time,
    action.payload.end_time,
  ])

  if (action.status !== 'awaiting_confirmation') {
    const joinUrl = String(result.join_url || '')
    const status = (
      action.status === 'succeeded'
        ? '✓ 会议已创建并写入日程'
        : action.status === 'cancelled'
          ? '已取消'
          : action.status === 'failed'
            ? '创建失败'
            : action.status === 'reconciliation_required'
              ? '外部结果需要确认'
              : '正在处理'
    )
    return <View className='meeting-result'>
      <Text className='action-status'>{status}</Text>
      {result.meeting_code ? <Text>会议号：{String(result.meeting_code)}</Text> : null}
      {joinUrl ? <Button className='secondary-button' onClick={() => {
        void Taro.setClipboardData({ data: joinUrl })
      }}>复制入会链接</Button> : null}
    </View>
  }

  const startIso = isoFromParts(startDate, startTime)
  const endIso = isoFromParts(endDate, endTime)
  const validTimes = Boolean(
    startIso && endIso && new Date(endIso).getTime() > new Date(startIso).getTime(),
  )
  const currentStart = isoFromParts(initialStart.date, initialStart.time)
  const currentEnd = isoFromParts(initialEnd.date, initialEnd.time)
  const dirty = (
    subject.trim() !== String(action.payload.subject || '腾讯会议')
    || startIso !== currentStart
    || endIso !== currentEnd
  )
  const needsValidation = dirty || missing.length > 0 || errors.length > 0
  const warningsAccepted = warnings.every((item) => acceptedWarnings.includes(item))
  const dateFallback = localDateTime(new Date().toISOString()).date

  return <View className='meeting-editor'>
    <Text className='field-label'>会议主题</Text>
    <Input className='meeting-subject' maxlength={120} disabled={busy}
      value={subject} onInput={(event) => setSubject(event.detail.value)} />
    <View className='meeting-time-grid'>
      <View>
        <Text className='field-label'>开始时间</Text>
        <View className='datetime-row'>
          <Picker mode='date' disabled={busy} value={startDate || dateFallback}
            onChange={(event) => setStartDate(String(event.detail.value))}>
            <View className='native-picker'>{startDate || '选择日期'}</View>
          </Picker>
          <Picker mode='time' disabled={busy} value={startTime || '09:00'}
            onChange={(event) => setStartTime(String(event.detail.value))}>
            <View className='native-picker'>{startTime || '选择时间'}</View>
          </Picker>
        </View>
      </View>
      <View>
        <Text className='field-label'>结束时间</Text>
        <View className='datetime-row'>
          <Picker mode='date' disabled={busy} value={endDate || startDate || dateFallback}
            onChange={(event) => setEndDate(String(event.detail.value))}>
            <View className='native-picker'>{endDate || '选择日期'}</View>
          </Picker>
          <Picker mode='time' disabled={busy} value={endTime || '10:00'}
            onChange={(event) => setEndTime(String(event.detail.value))}>
            <View className='native-picker'>{endTime || '选择时间'}</View>
          </Picker>
        </View>
      </View>
    </View>
    {errors.map((message) => <Text className='action-error' key={message}>{message}</Text>)}
    {startIso && endIso && !validTimes
      ? <Text className='action-error'>会议结束时间必须晚于开始时间</Text>
      : null}
    {!needsValidation ? <CheckboxGroup
      onChange={(event) => setAcceptedWarnings(event.detail.value)}
    >
      {warnings.map((warning) => <Label className='meeting-warning-choice' key={warning}>
        <Checkbox
          checked={acceptedWarnings.includes(warning)}
          value={warning}
          disabled={busy}
        />
        <Text>{warning}（确认后仍要创建）</Text>
      </Label>)}
    </CheckboxGroup> : null}
    <View className='action-buttons'>
      {needsValidation
        ? <Button className='primary-button' loading={busy} disabled={busy || !validTimes}
          onClick={() => onExecute(action, 'update_meeting_action', {
            subject: subject.trim() || '腾讯会议',
            start_time: startIso,
            end_time: endIso,
          })}>保存并检查冲突</Button>
        : <Button className='primary-button' loading={busy}
          disabled={busy || !validTimes || !warningsAccepted}
          onClick={() => onExecute(action, 'confirm_action')}>确认创建</Button>}
      <Button className='secondary-button' disabled={busy}
        onClick={() => onExecute(action, 'cancel_action')}>取消</Button>
    </View>
  </View>
}

export default function WorkspaceActionCard({ action, busy = false, onExecute }: Props) {
  const [imageIndex, setImageIndex] = useState(0)
  const payload = action.payload || {}
  const finished = ['succeeded', 'active', 'cancelled', 'failed'].includes(action.status)
  const imageVersions = imageVersionsFrom(action)
  const places = arrayOfRecords(payload.places)

  return <View className='structured-card action-card'>
    <Text className='card-eyebrow'>{actionName(action.kind)}</Text>
    <Text className='card-title'>{String(payload.title || payload.summary || payload.subject || payload.prompt || actionName(action.kind))}</Text>
    {action.kind === 'map_recommendation' && places.length
      ? <View className='action-place-list'>
        {places.map((place, index) => <Text key={String(place.place_id || index)}>
          {index + 1}. {String(place.name || '地点')}{place.address ? ` · ${String(place.address)}` : ''}
        </Text>)}
      </View>
      : null}
    {action.kind === 'calendar_changes' ? <CalendarDetails action={action} /> : null}
    {action.kind === 'meeting_create'
      ? <MeetingDetails action={action} busy={busy} onExecute={onExecute} />
      : null}
    {imageVersions.length ? <View className='image-version-gallery'>
      <Swiper
        className='image-version-swiper'
        current={Math.min(imageIndex, imageVersions.length - 1)}
        indicatorDots={imageVersions.length > 1}
        circular={imageVersions.length > 1}
        onChange={(event) => setImageIndex(event.detail.current)}
      >
        {imageVersions.map((version) => <SwiperItem key={version.id}>
          <MakersImage src={version.image_url} fit />
        </SwiperItem>)}
      </Swiper>
      {imageVersions.length > 1
        ? <Text className='image-version-count'>{imageIndex + 1} / {imageVersions.length} · 左右滑动查看版本</Text>
        : null}
    </View> : null}
    {action.kind === 'meeting_create'
      ? null
      : finished
        ? <Text className='action-status'>{action.status === 'cancelled' ? '已取消' : action.status === 'failed' ? '执行失败' : '✓ 已完成'}</Text>
        : <View className='action-buttons'>
          <Button
            className='primary-button'
            loading={busy}
            disabled={busy}
            onClick={() => onExecute(action, action.kind === 'map_recommendation' ? 'activate_map' : 'confirm_action')}
          >
            {action.kind === 'map_recommendation' ? '在地图中查看' : '确认执行'}
          </Button>
          <Button className='secondary-button' disabled={busy}
            onClick={() => onExecute(action, 'cancel_action')}>取消</Button>
        </View>}
  </View>
}
