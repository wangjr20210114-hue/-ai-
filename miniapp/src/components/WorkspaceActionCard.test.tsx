// @vitest-environment jsdom

import { renderToStaticMarkup } from 'react-dom/server'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@tarojs/taro', () => ({
  default: {
    setClipboardData: vi.fn(),
  },
}))

vi.mock('@tarojs/components', async () => {
  const React = await import('react')
  const element = (tag: string) => ({
    children,
    ...props
  }: Record<string, unknown> & { children?: ReactNode }) => React.createElement(
    tag,
    Object.fromEntries(Object.entries(props).filter(([key]) => !key.startsWith('on'))),
    children,
  )
  return {
    Button: element('button'),
    Checkbox: element('input'),
    CheckboxGroup: element('div'),
    Input: element('input'),
    Label: element('label'),
    Picker: element('div'),
    Swiper: element('div'),
    SwiperItem: element('div'),
    Text: element('span'),
    View: element('div'),
  }
})

vi.mock('./MakersImage', async () => {
  const React = await import('react')
  return {
    default: ({ src }: { src: string }) => React.createElement('img', { 'data-src': src }),
  }
})

import WorkspaceActionCard from './WorkspaceActionCard'

describe('native structured action cards', () => {
  it('shows every calendar mutation and warning before confirmation', () => {
    const html = renderToStaticMarkup(<WorkspaceActionCard
      action={{
        id: 'calendar-1',
        kind: 'calendar_changes',
        status: 'awaiting_confirmation',
        version: 1,
        payload: {
          summary: '明天行程',
          changes: [
            {
              operation: 'create',
              event: {
                title: '早餐',
                start_time: 1_900_000_000,
                duration_minutes: 30,
                place: { name: '早餐店', address: '北京市海淀区' },
              },
            },
            {
              operation: 'update',
              schedule_id: 'schedule-2',
              event: { title: '北京站', start_time: 1_900_003_600, duration_minutes: 20 },
            },
          ],
          warnings: ['早餐后到北京站的道路时间需要留意'],
        },
      }}
      onExecute={vi.fn()}
    />)
    expect(html).toContain('明天行程')
    expect(html).toContain('早餐')
    expect(html).toContain('北京站')
    expect(html).toContain('道路时间需要留意')
    expect(html).toContain('确认执行')
  })

  it('uses native date and time inputs before a missing meeting can be confirmed', () => {
    const html = renderToStaticMarkup(<WorkspaceActionCard
      action={{
        id: 'meeting-1',
        kind: 'meeting_create',
        status: 'awaiting_confirmation',
        version: 1,
        payload: {
          subject: '产品讨论',
          start_time: '',
          end_time: '',
          missing_fields: ['start_time', 'end_time'],
          validation_errors: [],
          warnings: [],
        },
      }}
      onExecute={vi.fn()}
    />)
    expect(html).toContain('产品讨论')
    expect(html).toContain('开始时间')
    expect(html).toContain('结束时间')
    expect(html).toContain('选择日期')
    expect(html).toContain('保存并检查冲突')
    expect(html).not.toContain('确认创建')
  })

  it('keeps verified map places in Agent order and offers the native map action', () => {
    const html = renderToStaticMarkup(<WorkspaceActionCard
      action={{
        id: 'map-1',
        kind: 'map_recommendation',
        status: 'awaiting_confirmation',
        version: 1,
        payload: {
          title: '今晚路线',
          places: [
            { place_id: 'breakfast', name: '早餐店', address: '第一站' },
            { place_id: 'station', name: '北京站', address: '第二站' },
            { place_id: 'hotel', name: '锦江之星', address: '第三站' },
          ],
          show_route: true,
        },
      }}
      onExecute={vi.fn()}
    />)
    expect(html.indexOf('早餐店')).toBeLessThan(html.indexOf('北京站'))
    expect(html.indexOf('北京站')).toBeLessThan(html.indexOf('锦江之星'))
    expect(html).toContain('在地图中查看')
  })

  it('renders the Makers image version chain in one native swiper', () => {
    const html = renderToStaticMarkup(<WorkspaceActionCard
      action={{
        id: 'image-2',
        kind: 'image_generate',
        status: 'succeeded',
        version: 2,
        payload: { prompt: '橘猫戴蓝色围巾' },
        result: {
          image_url: '/files?key=second',
          versions: [
            { id: 'image-1', prompt: '橘猫', image_url: '/files?key=first' },
            { id: 'image-2', prompt: '橘猫戴蓝色围巾', image_url: '/files?key=second' },
          ],
        },
      }}
      onExecute={vi.fn()}
    />)
    expect(html).toContain('data-src="/files?key=first"')
    expect(html).toContain('data-src="/files?key=second"')
    expect(html).toContain('1 / 2')
    expect(html).toContain('左右滑动查看版本')
  })
})
