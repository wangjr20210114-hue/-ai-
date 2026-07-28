import { Button, Text, View } from '@tarojs/components'
import type { WorkspaceAction } from '@floris/contracts'
import MakersImage from './MakersImage'

interface Props {
  action: WorkspaceAction
  busy?: boolean
  onExecute: (action: WorkspaceAction, operation: 'activate_map' | 'confirm_action' | 'cancel_action') => void
}

const actionName = (kind: WorkspaceAction['kind']) => ({
  map_recommendation: '地点与路线',
  calendar_changes: '日程变更',
  meeting_create: '腾讯会议',
  image_generate: '图片创作',
}[kind])

export default function WorkspaceActionCard({ action, busy = false, onExecute }: Props) {
  const payload = action.payload || {}
  const result = action.result || {}
  const finished = ['succeeded', 'active', 'cancelled', 'failed'].includes(action.status)
  const imageUrl = String(result.image_url || '')
  return <View className='structured-card action-card'>
    <Text className='card-eyebrow'>{actionName(action.kind)}</Text>
    <Text className='card-title'>{String(payload.title || payload.subject || payload.prompt || actionName(action.kind))}</Text>
    {imageUrl ? <MakersImage src={imageUrl} /> : null}
    {finished
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
        <Button className='secondary-button' disabled={busy} onClick={() => onExecute(action, 'cancel_action')}>取消</Button>
      </View>}
  </View>
}
