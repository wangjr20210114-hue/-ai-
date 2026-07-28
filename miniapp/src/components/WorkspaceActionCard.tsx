import { useState } from 'react'
import { Button, Swiper, SwiperItem, Text, View } from '@tarojs/components'
import { imageVersionsFrom, type WorkspaceAction } from '@floris/contracts'
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
  const [imageIndex, setImageIndex] = useState(0)
  const payload = action.payload || {}
  const finished = ['succeeded', 'active', 'cancelled', 'failed'].includes(action.status)
  const imageVersions = imageVersionsFrom(action)
  return <View className='structured-card action-card'>
    <Text className='card-eyebrow'>{actionName(action.kind)}</Text>
    <Text className='card-title'>{String(payload.title || payload.subject || payload.prompt || actionName(action.kind))}</Text>
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
