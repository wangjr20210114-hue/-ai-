import { useEffect, useMemo, useState } from 'react'
import Taro from '@tarojs/taro'
import { Button, Picker, Slider, Switch, Text, View } from '@tarojs/components'
import type { MiniappSession } from '@floris/contracts'
import { getOrCreateConversationId } from '@/services/conversations'
import { apiRequest } from '@/services/request'
import { ensureSession } from '@/services/session'
import './index.scss'

type Skill = {
  id: string
  locked?: boolean
  configured?: boolean
  external?: boolean
  requires?: string[]
  name?: Record<string, string>
  description?: Record<string, string>
}

type Intelligence = {
  skill_preferences?: Record<string, boolean>
  skill_catalog?: Skill[]
  search_preferences?: { result_limit?: number; image_limit?: number; parallel_image_search?: boolean }
  map_preferences?: { service_mode?: string; place_result_limit?: number; route_stop_limit?: number }
  memory_preferences?: { enabled?: boolean }
}

const languages = [
  ['zh-CN', '简体中文'],
  ['zh-TW', '繁體中文'],
  ['en', 'English'],
  ['cat-cute', '可爱喵喵语'],
  ['cat-cold', '冷酷喵喵语'],
]

export default function SettingsPage() {
  const [session, setSession] = useState<MiniappSession | null>(null)
  const [conversationId, setConversationId] = useState('')
  const [state, setState] = useState<Intelligence>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState('')
  const [error, setError] = useState('')
  const [language, setLanguage] = useState(String(Taro.getStorageSync('floris-language') || 'zh-CN'))
  const preferences = state.skill_preferences || {}
  const skills = state.skill_catalog || []
  const searchEnabled = Boolean(preferences['web-search'])
  const mapsEnabled = Boolean(preferences.maps)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const nextSession = await ensureSession()
      const id = getOrCreateConversationId(nextSession)
      const data = await apiRequest<Intelligence>('/intelligence', {
        method: 'POST',
        conversationId: id,
        data: { operation: 'get' },
      })
      setSession(nextSession)
      setConversationId(id)
      setState(data)
    } catch (reason) {
      setError(String((reason as Error)?.message || reason))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const update = async (operation: string, field: string, payload: Record<string, unknown>) => {
    if (!conversationId || saving) return
    setSaving(field)
    try {
      const data = await apiRequest<Intelligence>('/intelligence', {
        method: 'POST',
        conversationId,
        data: { operation, ...payload },
      })
      setState(data)
      void Taro.showToast({ title: '已保存', icon: 'success' })
    } catch (reason) {
      void Taro.showToast({ title: String((reason as Error)?.message || '保存失败'), icon: 'none' })
    } finally {
      setSaving('')
    }
  }

  const toggleSkill = (skill: Skill, enabled: boolean) => {
    if (skill.locked) return
    const next = { ...preferences, [skill.id]: enabled }
    void update('update_skill_preferences', `skill:${skill.id}`, { preferences: next })
  }

  const languageIndex = Math.max(0, languages.findIndex(([id]) => id === language))
  const skillById = useMemo(() => new Map(skills.map((skill) => [skill.id, skill])), [skills])

  if (loading) return <View className='settings-state'>正在读取设置…</View>
  if (error) return <View className='settings-state'><Text>{error}</Text><Button onClick={() => void load()}>重试</Button></View>

  return <View className='settings-page'>
    <View className='setting-section'>
      <Text className='section-title'>工作区</Text>
      <View className='workspace-links'>
        <Button onClick={() => Taro.navigateTo({ url: '/pages/calendar/index' })}>我的日程</Button>
        <Button onClick={() => Taro.navigateTo({ url: '/pages/library/index' })}>我的阅读</Button>
      </View>
    </View>
    <View className='setting-section'>
      <Text className='section-title'>界面与回答语言</Text>
      <Picker
        mode='selector'
        range={languages.map(([, label]) => label)}
        value={languageIndex}
        onChange={(event) => {
          const next = languages[Number(event.detail.value)]?.[0] || 'zh-CN'
          setLanguage(next)
          Taro.setStorageSync('floris-language', next)
        }}
      >
        <View className='picker-row'><Text>语言</Text><Text>{languages[languageIndex][1]} 〉</Text></View>
      </Picker>
    </View>

    <View className='setting-section'>
      <Text className='section-title'>Skills 广场</Text>
      <Text className='section-hint'>能力开关直接使用现有 Skills Agent 和 Makers 状态；开启依赖能力时由后端自动补齐。</Text>
      {skills.map((skill) => {
        const enabled = skill.locked || Boolean(preferences[skill.id])
        const missingDependency = (skill.requires || []).find((id) => !preferences[id] && !skillById.get(id)?.locked)
        return <View className='skill-row' key={skill.id}>
          <View className='skill-copy'>
            <Text className='skill-name'>{skill.name?.[language] || skill.name?.['zh-CN'] || skill.id}</Text>
            <Text className='skill-description'>{skill.description?.[language] || skill.description?.['zh-CN'] || ''}</Text>
            {missingDependency ? <Text className='skill-warning'>需要先开启：{skillById.get(missingDependency)?.name?.[language] || skillById.get(missingDependency)?.name?.['zh-CN'] || missingDependency}</Text> : null}
            {skill.external && !skill.configured ? <Text className='skill-warning'>需要在网页端完成服务授权</Text> : null}
          </View>
          <Switch
            checked={enabled}
            disabled={skill.locked || saving.startsWith('skill:')}
            color='#e88240'
            onChange={(event) => toggleSkill(skill, event.detail.value)}
          />
        </View>
      })}
    </View>

    <View className={`setting-section ${searchEnabled ? '' : 'disabled-section'}`}>
      <Text className='section-title'>搜索体验</Text>
      <Text className='section-hint'>仅在“实时搜索”Skill 开启时可调；仍复用现有 rich_search 并发链。</Text>
      <Text className='range-label'>网页结果：{state.search_preferences?.result_limit || 8} 条</Text>
      <Slider min={4} max={18} step={2} showValue disabled={!searchEnabled || Boolean(saving)}
        value={state.search_preferences?.result_limit || 8}
        onChange={(event) => void update('update_search_preferences', 'search-result', {
          preferences: { ...(state.search_preferences || {}), result_limit: event.detail.value },
        })} />
      <Text className='range-label'>候选图片：{state.search_preferences?.image_limit ?? 8} 张</Text>
      <Slider min={0} max={8} step={1} showValue disabled={!searchEnabled || Boolean(saving)}
        value={state.search_preferences?.image_limit ?? 8}
        onChange={(event) => void update('update_search_preferences', 'search-image', {
          preferences: { ...(state.search_preferences || {}), image_limit: event.detail.value },
        })} />
      <View className='switch-row'><Text>并行查找图片</Text><Switch
        checked={state.search_preferences?.parallel_image_search !== false}
        disabled={!searchEnabled || Boolean(saving)}
        color='#e88240'
        onChange={(event) => void update('update_search_preferences', 'search-parallel', {
          preferences: { ...(state.search_preferences || {}), parallel_image_search: event.detail.value },
        })}
      /></View>
    </View>

    <View className={`setting-section ${mapsEnabled ? '' : 'disabled-section'}`}>
      <Text className='section-title'>地图与路线</Text>
      <Text className='section-hint'>小程序使用原生 map 组件；地点核实和道路规划继续由现有 Maps Skill 完成。</Text>
      <Picker
        disabled={!mapsEnabled || Boolean(saving)}
        mode='selector'
        range={['快速', '均衡', '完整']}
        value={['fast', 'balanced', 'complete'].indexOf(state.map_preferences?.service_mode || 'balanced')}
        onChange={(event) => void update('update_map_preferences', 'map-mode', {
          preferences: {
            ...(state.map_preferences || {}),
            service_mode: ['fast', 'balanced', 'complete'][Number(event.detail.value)],
          },
        })}
      >
        <View className='picker-row'><Text>服务档位</Text><Text>{({ fast: '快速', balanced: '均衡', complete: '完整' } as Record<string, string>)[state.map_preferences?.service_mode || 'balanced']} 〉</Text></View>
      </Picker>
    </View>

    <View className='account-note'>
      <Text>微信身份：{session?.userId.slice(-8)}</Text>
      <Text>业务数据保存在 EdgeOne Makers，不在小程序中另建数据库。</Text>
    </View>
  </View>
}
