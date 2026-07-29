import { useEffect, useMemo, useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Image, Input, Picker, Slider, Switch, Text, View } from '@tarojs/components'
import {
  readProfile,
  saveAvatarFromChoose,
  saveNickName,
  subscribeProfile,
  type UserProfile,
} from '@/services/profile'
import type { MiniappSession } from '@floris/contracts'
import { capabilityEnabled } from '@floris/contracts'
import { getOrCreateConversationId } from '@/services/conversations'
import {
  proactiveOperation,
  type ProactivePreferences,
  type ProactiveState,
} from '@/services/proactive'
import { apiRequest } from '@/services/request'
import { ensureSession } from '@/services/session'
import { readNativeCache, writeNativeCache } from '@/services/native-cache'
import SkeletonState from '@/components/SkeletonState'
import { useTabEnterClass } from '@/hooks/useTabEnterClass'
import {
  getProviderUsage,
  meteredProviderValue,
  type ProviderUsageSummary,
} from '@/services/provider-usage'
import { clearMiniappLocalData, resetApplicationData } from '@/services/reset'
import {
  LANGUAGE_KEY,
  readLanguage,
  supportedLanguages,
  translate,
  type Language,
  type TranslationKey,
} from '@/i18n'
import './index.scss'
import { updateNativeTabBar } from '@/services/tabbar'

type Skill = {
  id: string
  locked?: boolean
  configured?: boolean
  external?: boolean
  requires?: string[]
  capabilities?: string[]
  name?: Record<string, string>
  description?: Record<string, string>
}

type Intelligence = {
  skill_preferences?: Record<string, boolean>
  skill_catalog?: Skill[]
  search_preferences?: { result_limit?: number; image_limit?: number; parallel_image_search?: boolean }
  map_preferences?: {
    service_mode?: string
    place_result_limit?: number
    route_stop_limit?: number
    search_timeout_seconds?: number
    preferred_route_mode?: string
    route_strategy?: string
    near_time_tolerance_minutes?: number
    learn_route_preferences?: boolean
  }
  memory_preferences?: { enabled?: boolean }
}

const SETTINGS_SNAPSHOT_KEY = 'floris.miniapp.screen.settings.v1'

type SettingsSnapshot = {
  conversationId: string
  intelligence: Intelligence
  proactive: ProactiveState
}

export default function SettingsPage() {
  const enterClass = useTabEnterClass()
  const [initial] = useState(() => readNativeCache<SettingsSnapshot>(SETTINGS_SNAPSHOT_KEY))
  const [session, setSession] = useState<MiniappSession | null>(null)
  const [conversationId, setConversationId] = useState(initial?.conversationId || '')
  const [state, setState] = useState<Intelligence>(initial?.intelligence || {})
  const [loading, setLoading] = useState(!initial)
  const [saving, setSaving] = useState('')
  const [error, setError] = useState('')
  const [language, setLanguage] = useState<Language>(readLanguage())
  const [proactive, setProactive] = useState<ProactiveState>(initial?.proactive || {})
  const [mottos, setMottos] = useState<string[]>(
    (initial?.proactive.preferences?.fallback_mottos || []).slice(0, 5),
  )
  const [providerUsage, setProviderUsage] = useState<ProviderUsageSummary | null>(null)
  const [providerUsageLoading, setProviderUsageLoading] = useState(false)
  const [providerUsageError, setProviderUsageError] = useState(false)
  const [resetVisible, setResetVisible] = useState(false)
  const [resetPassword, setResetPassword] = useState('')
  const [profile, setProfile] = useState<UserProfile>(() => readProfile())
  useEffect(() => subscribeProfile(setProfile), [])
  const preferences = state.skill_preferences || {}
  const skills = state.skill_catalog || []
  const searchEnabled = capabilityEnabled(skills, preferences, 'web_search')
  const mapsEnabled = capabilityEnabled(skills, preferences, 'places')

  const load = async () => {
    if (!initial && !session) setLoading(true)
    setError('')
    try {
      const nextSession = await ensureSession()
      const id = getOrCreateConversationId(nextSession)
      const [data, proactiveState] = await Promise.all([
        apiRequest<Intelligence>('/intelligence', {
          method: 'POST',
          conversationId: id,
          data: { operation: 'get' },
        }),
        proactiveOperation(id, 'get').catch(() => ({} as ProactiveState)),
      ])
      setSession(nextSession)
      setConversationId(id)
      setState(data)
      setProactive(proactiveState)
      setMottos((proactiveState.preferences?.fallback_mottos || []).slice(0, 5))
      writeNativeCache<SettingsSnapshot>(SETTINGS_SNAPSHOT_KEY, {
        conversationId: id,
        intelligence: data,
        proactive: proactiveState,
      })
      void loadProviderUsage(id)
    } catch (reason) {
      setError(String((reason as Error)?.message || reason))
    } finally {
      setLoading(false)
    }
  }

  useDidShow(() => {
    const nextLanguage = readLanguage()
    setLanguage(nextLanguage)
    void Taro.setNavigationBarTitle({ title: translate('navSettings', {}, nextLanguage) })
    void updateNativeTabBar(nextLanguage)
    void load()
  })

  const loadProviderUsage = async (id = conversationId) => {
    if (!id || providerUsageLoading) return
    setProviderUsageLoading(true)
    setProviderUsageError(false)
    try {
      setProviderUsage(await getProviderUsage(id))
    } catch {
      setProviderUsageError(true)
    } finally {
      setProviderUsageLoading(false)
    }
  }

  const clearData = async () => {
    if (!conversationId || saving) return
    if (!resetPassword) {
      void Taro.showToast({ title: translate('dataClearPasswordRequired', {}, language), icon: 'none' })
      return
    }
    const answer = await Taro.showModal({
      title: translate('dataClearWarningTitle', {}, language),
      content: translate('dataClearWarningBody', {}, language),
      confirmText: translate('confirmClearDatabase', {}, language),
      cancelText: translate('cancel', {}, language),
      confirmColor: '#c95147',
    })
    if (!answer.confirm) return
    setSaving('reset')
    try {
      await resetApplicationData(conversationId, resetPassword)
      clearMiniappLocalData(language)
      void Taro.showToast({ title: translate('dataClearSucceeded', {}, language), icon: 'success', duration: 1800 })
      await ensureSession(true)
      await Taro.reLaunch({ url: '/pages/index/index' })
    } catch {
      void Taro.showToast({ title: translate('dataClearFailed', {}, language), icon: 'none' })
    } finally {
      setSaving('')
    }
  }

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
      writeNativeCache<SettingsSnapshot>(SETTINGS_SNAPSHOT_KEY, {
        conversationId,
        intelligence: data,
        proactive,
      })
      void Taro.showToast({ title: translate('saved', {}, language), icon: 'success' })
    } catch (reason) {
      void Taro.showToast({ title: String((reason as Error)?.message || translate('saveFailed', {}, language)), icon: 'none' })
    } finally {
      setSaving('')
    }
  }

  const toggleSkill = (skill: Skill, enabled: boolean) => {
    if (skill.locked) return
    const next = { ...preferences, [skill.id]: enabled }
    void update('update_skill_preferences', `skill:${skill.id}`, { preferences: next })
  }

  const updateProactive = async (
    field: string,
    changes: Partial<ProactivePreferences>,
  ) => {
    if (!conversationId || saving) return
    setSaving(field)
    try {
      const data = await proactiveOperation(conversationId, 'update_preferences', {
        preferences: { ...(proactive.preferences || {}), ...changes },
      })
      setProactive(data)
      setMottos((data.preferences?.fallback_mottos || []).slice(0, 5))
      writeNativeCache<SettingsSnapshot>(SETTINGS_SNAPSHOT_KEY, {
        conversationId,
        intelligence: state,
        proactive: data,
      })
      void Taro.showToast({ title: translate('saved', {}, language), icon: 'success' })
    } catch (reason) {
      void Taro.showToast({ title: String((reason as Error)?.message || translate('saveFailed', {}, language)), icon: 'none' })
    } finally {
      setSaving('')
    }
  }

  const refreshProactive = async () => {
    if (!conversationId || saving) return
    setSaving('proactive-refresh')
    try {
      const data = await proactiveOperation(conversationId, 'refresh')
      setProactive(data)
      writeNativeCache<SettingsSnapshot>(SETTINGS_SNAPSHOT_KEY, {
        conversationId,
        intelligence: state,
        proactive: data,
      })
      void Taro.showToast({ title: translate('checkDone', {}, language), icon: 'success' })
    } catch {
      void Taro.showToast({ title: translate('checkUnavailable', {}, language), icon: 'none' })
    } finally {
      setSaving('')
    }
  }

  const languageIndex = Math.max(0, supportedLanguages.findIndex(({ id }) => id === language))
  const languageLabels = supportedLanguages.map(({ nameKey }) => translate(nameKey, {}, language))
  const mapModes: Array<{ id: string; key: TranslationKey }> = [
    { id: 'fast', key: 'fast' },
    { id: 'balanced', key: 'balanced' },
    { id: 'complete', key: 'complete' },
  ]
  const lookaheadOptions = [12, 24, 48, 72]
  const bufferOptions = [0, 10, 15, 30, 45, 60]
  const placeResultOptions = [3, 4, 6, 8, 10, 12]
  const routeStopOptions = [4, 6, 8, 10, 12]
  const mapTimeoutOptions = [15, 20, 30, 45, 55]
  const routeToleranceOptions = [0, 5, 10, 15, 20, 30]
  const routeModes: Array<{ id: string; key: TranslationKey }> = [
    { id: 'driving', key: 'routeModeDriving' },
    { id: 'transit', key: 'routeModeTransit' },
    { id: 'walking', key: 'routeModeWalking' },
    { id: 'bicycling', key: 'routeModeBicycling' },
  ]
  const routeStrategies: Array<{ id: string; key: TranslationKey }> = [
    { id: 'time_then_cost', key: 'routeStrategyTimeThenCost' },
    { id: 'least_time', key: 'routeStrategyLeastTime' },
    { id: 'least_cost', key: 'routeStrategyLeastCost' },
  ]
  const skillById = useMemo(() => new Map(skills.map((skill) => [skill.id, skill])), [skills])
  const proactiveEnabled = capabilityEnabled(skills, preferences, 'workflow_action')
  const proactivePreferences = proactive.preferences || {}

  if (loading) return <View className='settings'><SkeletonState rows={6} /></View>
  if (error) return <View className='settings-state'><Text>{error}</Text><Button onClick={() => void load()}>{translate('retry', {}, language)}</Button></View>

  return <View className={`settings-page ${enterClass}`}>
    <View className='settings-hero'>
      <View>
        <Text className='settings-kicker'>{translate('navSettings', {}, language)}</Text>
        <Text className='settings-title'>{translate('settingsOverview', {}, language)}</Text>
      </View>
      <Text className='settings-mark'>⌘</Text>
    </View>
    <View className='setting-section profile-section'>
      <Text className='section-title'>{translate('profileSection', {}, language)}</Text>
      <View className='profile-row'>
        <Button
          className='profile-avatar-btn'
          openType='chooseAvatar'
          aria-label={translate('profileAvatarHint', {}, language)}
          onChooseAvatar={(event) => {
            const avatarUrl = event.detail?.avatarUrl
            if (avatarUrl) void saveAvatarFromChoose(avatarUrl).then(setProfile)
          }}
        >
          {profile.avatarUrl
            ? <Image className='profile-avatar-img' src={profile.avatarUrl} mode='aspectFill' />
            : <Text className='profile-avatar-fallback'>🐾</Text>}
          <Text className='profile-avatar-badge'>＋</Text>
        </Button>
        <View className='profile-fields'>
          <Input
            className='profile-nickname'
            type='nickname'
            value={profile.nickName}
            placeholder={translate('profileNicknamePlaceholder', {}, language)}
            onBlur={(event) => setProfile(saveNickName(event.detail.value))}
            onConfirm={(event) => setProfile(saveNickName(event.detail.value))}
          />
          <Text className='profile-hint'>{translate('profileSyncHint', {}, language)}</Text>
        </View>
      </View>
    </View>
    <View className='setting-section workspace-section'>
      <Text className='section-title'>{translate('workspace', {}, language)}</Text>
      <View className='workspace-links'>
        <Button onClick={() => Taro.switchTab({ url: '/pages/calendar/index' })}>{translate('myCalendar', {}, language)}</Button>
        <Button onClick={() => Taro.switchTab({ url: '/pages/library/index' })}>{translate('myReading', {}, language)}</Button>
      </View>
    </View>
    <View className='setting-section language-section'>
      <Text className='section-title'>{translate('interfaceLanguage', {}, language)}</Text>
      <Picker
        mode='selector'
        range={languageLabels}
        value={languageIndex}
        onChange={(event) => {
          const next = supportedLanguages[Number(event.detail.value)]?.id || 'zh-CN'
          setLanguage(next)
          Taro.setStorageSync(LANGUAGE_KEY, next)
          void Taro.setNavigationBarTitle({ title: translate('navSettings', {}, next) })
          void updateNativeTabBar(next)
        }}
      >
        <View className='picker-row'><Text>{translate('language', {}, language)}</Text><Text>{languageLabels[languageIndex]} 〉</Text></View>
      </Picker>
    </View>

    <View className='setting-section usage-section'>
      <View className='usage-heading'>
        <View>
          <Text className='section-title'>{translate('providerUsage', {}, language)}</Text>
          <Text className='section-hint'>{translate('providerUsageHint', {}, language)}</Text>
        </View>
        <Button
          className='usage-refresh'
          loading={providerUsageLoading}
          disabled={providerUsageLoading}
          onClick={() => void loadProviderUsage()}
        >↻</Button>
      </View>
      {providerUsage ? <View className='usage-grid'>
        {[
          [translate('providerUsageToday', {}, language), providerUsage.usage.daily_tokens],
          [translate('providerUsageMonth', {}, language), providerUsage.usage.monthly_tokens],
          [translate('visionTokenUsage', {}, language), meteredProviderValue(providerUsage, 'monthly', 'vision_tokens')],
          [translate('imageGenerationUsage', {}, language), meteredProviderValue(providerUsage, 'monthly', 'images')],
          [translate('wsaUsage', {}, language), Number(providerUsage.metering.monthly['wsa.requests'] || 0)],
          [translate('mapUsage', {}, language), Number(providerUsage.metering.monthly['tencent_maps.requests'] || 0)],
        ].map(([label, value]) => <View className='usage-card' key={String(label)}>
          <Text>{label}</Text>
          <Text>{Number(value).toLocaleString()}</Text>
        </View>)}
        {providerUsage.providers.flatMap((provider) => provider.balances.map((balance) => <View
          className='usage-card'
          key={`${provider.id}-${balance.currency}`}
        >
          <Text>{translate('providerBalance', { provider: provider.id }, language)}</Text>
          <Text>{balance.currency} {Number(balance.total_balance).toFixed(2)}</Text>
        </View>))}
      </View> : null}
      {providerUsageError ? <Text className='usage-error'>
        {translate('providerUsageLoadFailed', {}, language)}
      </Text> : null}
      {providerUsage ? <Text className='usage-updated'>{translate('providerUsageUpdated', {
        time: new Date(providerUsage.refreshed_at * 1000).toLocaleString(),
      }, language)}</Text> : null}
    </View>

    <View className='setting-section skills-section'>
      <Text className='section-title'>{translate('skillsMarketplace', {}, language)}</Text>
      <Text className='section-hint'>{translate('skillsHint', {}, language)}</Text>
      {skills.map((skill) => {
        const enabled = skill.locked || Boolean(preferences[skill.id])
        const missingDependency = (skill.requires || []).find((id) => !preferences[id] && !skillById.get(id)?.locked)
        return <View className='skill-row' key={skill.id}>
          <View className='skill-copy'>
            <Text className='skill-name'>{skill.name?.[language] || skill.name?.['zh-CN'] || skill.id}</Text>
            <Text className='skill-description'>{skill.description?.[language] || skill.description?.['zh-CN'] || ''}</Text>
            {missingDependency ? <Text className='skill-warning'>{translate('requiresSkill', {
              name: skillById.get(missingDependency)?.name?.[language]
                || skillById.get(missingDependency)?.name?.['zh-CN']
                || missingDependency,
            }, language)}</Text> : null}
            {skill.external && !skill.configured ? <Text className='skill-warning'>{translate('authorizeOnWeb', {}, language)}</Text> : null}
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
      <Text className='section-title'>{translate('searchExperience', {}, language)}</Text>
      <Text className='section-hint'>{translate('searchHint', {}, language)}</Text>
      <Text className='range-label'>{translate('webResultCount', {
        count: state.search_preferences?.result_limit || 8,
      }, language)}</Text>
      <Slider min={4} max={18} step={2} showValue disabled={!searchEnabled || Boolean(saving)}
        value={state.search_preferences?.result_limit || 8}
        onChange={(event) => void update('update_search_preferences', 'search-result', {
          preferences: { ...(state.search_preferences || {}), result_limit: event.detail.value },
        })} />
      <Text className='range-label'>{translate('imageCandidateCount', {
        count: state.search_preferences?.image_limit ?? 8,
      }, language)}</Text>
      <Slider min={0} max={8} step={1} showValue disabled={!searchEnabled || Boolean(saving)}
        value={state.search_preferences?.image_limit ?? 8}
        onChange={(event) => void update('update_search_preferences', 'search-image', {
          preferences: { ...(state.search_preferences || {}), image_limit: event.detail.value },
        })} />
      <View className='switch-row'><Text>{translate('parallelImages', {}, language)}</Text><Switch
        checked={state.search_preferences?.parallel_image_search !== false}
        disabled={!searchEnabled || Boolean(saving)}
        color='#e88240'
        onChange={(event) => void update('update_search_preferences', 'search-parallel', {
          preferences: { ...(state.search_preferences || {}), parallel_image_search: event.detail.value },
        })}
      /></View>
    </View>

    <View className={`setting-section ${mapsEnabled ? '' : 'disabled-section'}`}>
      <Text className='section-title'>{translate('mapsRoutes', {}, language)}</Text>
      <Text className='section-hint'>{translate('mapsHint', {}, language)}</Text>
      <Picker
        disabled={!mapsEnabled || Boolean(saving)}
        mode='selector'
        range={mapModes.map(({ key }) => translate(key, {}, language))}
        value={mapModes.findIndex(({ id }) => id === (state.map_preferences?.service_mode || 'balanced'))}
        onChange={(event) => {
          const serviceMode = mapModes[Number(event.detail.value)]?.id || 'balanced'
          const defaults = serviceMode === 'fast'
            ? { place_result_limit: 4, route_stop_limit: 4, search_timeout_seconds: 20 }
            : serviceMode === 'complete'
              ? { place_result_limit: 10, route_stop_limit: 12, search_timeout_seconds: 55 }
              : { place_result_limit: 6, route_stop_limit: 8, search_timeout_seconds: 30 }
          void update('update_map_preferences', 'map-mode', {
            preferences: {
              ...(state.map_preferences || {}),
              service_mode: serviceMode,
              ...defaults,
            },
          })
        }}
      >
        <View className='picker-row'><Text>{translate('serviceMode', {}, language)}</Text><Text>{translate(
          mapModes.find(({ id }) => id === (state.map_preferences?.service_mode || 'balanced'))?.key || 'balanced',
          {},
          language,
        )} 〉</Text></View>
      </Picker>
      {([
        ['mapPlaceResultCount', placeResultOptions, state.map_preferences?.place_result_limit || 6, 'place_result_limit'],
        ['mapRouteStopCount', routeStopOptions, state.map_preferences?.route_stop_limit || 8, 'route_stop_limit'],
        ['mapSearchTimeout', mapTimeoutOptions, state.map_preferences?.search_timeout_seconds || 30, 'search_timeout_seconds'],
        ['nearTimeTolerance', routeToleranceOptions, state.map_preferences?.near_time_tolerance_minutes ?? 10, 'near_time_tolerance_minutes'],
      ] as Array<[TranslationKey, number[], number, string]>).map(([label, options, value, field]) => <Picker
        key={field}
        disabled={!mapsEnabled || Boolean(saving)}
        mode='selector'
        range={options.map((item) => translate(
          field === 'search_timeout_seconds' ? 'secondsValue' : field === 'near_time_tolerance_minutes'
            ? 'routeToleranceMinutes'
            : 'numericValue',
          { value: item },
          language,
        ))}
        value={Math.max(0, options.indexOf(value))}
        onChange={(event) => void update('update_map_preferences', `map-${field}`, {
          preferences: {
            ...(state.map_preferences || {}),
            [field]: options[Number(event.detail.value)],
          },
        })}
      >
        <View className='picker-row'>
          <Text>{translate(label, {}, language)}</Text>
          <Text>{translate(
            field === 'search_timeout_seconds' ? 'secondsValue' : field === 'near_time_tolerance_minutes'
              ? 'routeToleranceMinutes'
              : 'numericValue',
            { value },
            language,
          )} 〉</Text>
        </View>
      </Picker>)}
      <Picker
        disabled={!mapsEnabled || Boolean(saving)}
        mode='selector'
        range={routeModes.map(({ key }) => translate(key, {}, language))}
        value={Math.max(0, routeModes.findIndex(({ id }) => id === (state.map_preferences?.preferred_route_mode || 'driving')))}
        onChange={(event) => void update('update_map_preferences', 'map-route-mode', {
          preferences: {
            ...(state.map_preferences || {}),
            preferred_route_mode: routeModes[Number(event.detail.value)]?.id || 'driving',
          },
        })}
      >
        <View className='picker-row'>
          <Text>{translate('preferredRouteMode', {}, language)}</Text>
          <Text>{translate(
            routeModes.find(({ id }) => id === (state.map_preferences?.preferred_route_mode || 'driving'))?.key || 'routeModeDriving',
            {},
            language,
          )} 〉</Text>
        </View>
      </Picker>
      <Picker
        disabled={!mapsEnabled || Boolean(saving)}
        mode='selector'
        range={routeStrategies.map(({ key }) => translate(key, {}, language))}
        value={Math.max(0, routeStrategies.findIndex(({ id }) => id === (state.map_preferences?.route_strategy || 'time_then_cost')))}
        onChange={(event) => void update('update_map_preferences', 'map-route-strategy', {
          preferences: {
            ...(state.map_preferences || {}),
            route_strategy: routeStrategies[Number(event.detail.value)]?.id || 'time_then_cost',
          },
        })}
      >
        <View className='picker-row'>
          <Text>{translate('routeStrategy', {}, language)}</Text>
          <Text>{translate(
            routeStrategies.find(({ id }) => id === (state.map_preferences?.route_strategy || 'time_then_cost'))?.key || 'routeStrategyTimeThenCost',
            {},
            language,
          )} 〉</Text>
        </View>
      </Picker>
      <View className='switch-row'>
        <Text>{translate('learnRoutePreferences', {}, language)}</Text>
        <Switch
          checked={state.map_preferences?.learn_route_preferences !== false}
          disabled={!mapsEnabled || Boolean(saving)}
          color='#e88240'
          onChange={(event) => void update('update_map_preferences', 'map-learning', {
            preferences: {
              ...(state.map_preferences || {}),
              learn_route_preferences: event.detail.value,
            },
          })}
        />
      </View>
    </View>

    <View className={`setting-section ${proactiveEnabled ? '' : 'disabled-section'}`}>
      <Text className='section-title'>{translate('proactiveService', {}, language)}</Text>
      <Text className='section-hint'>{translate('proactiveSettingsHint', {}, language)}</Text>
      <Picker
        disabled={!proactiveEnabled || Boolean(saving)}
        mode='selector'
        range={lookaheadOptions.map((hours) => hours === 72
          ? translate('nextDays', { count: 3 }, language)
          : translate('nextHours', { count: hours }, language))}
        value={Math.max(0, lookaheadOptions.indexOf(proactivePreferences.lookahead_hours || 24))}
        onChange={(event) => void updateProactive('proactive-lookahead', {
          lookahead_hours: lookaheadOptions[Number(event.detail.value)],
        })}
      >
        <View className='picker-row'>
          <Text>{translate('focusRange', {}, language)}</Text>
          <Text>{translate('hoursValue', {
            count: proactivePreferences.lookahead_hours || 24,
          }, language)} 〉</Text>
        </View>
      </Picker>
      <Picker
        disabled={!proactiveEnabled || Boolean(saving)}
        mode='selector'
        range={bufferOptions.map((minutes) => minutes
          ? translate('minutesValue', { count: minutes }, language)
          : translate('noExtraBuffer', {}, language))}
        value={Math.max(0, bufferOptions.indexOf(proactivePreferences.travel_buffer_minutes ?? 15))}
        onChange={(event) => void updateProactive('proactive-buffer', {
          travel_buffer_minutes: bufferOptions[Number(event.detail.value)],
        })}
      >
        <View className='picker-row'>
          <Text>{translate('travelBuffer', {}, language)}</Text>
          <Text>{translate('minutesValue', {
            count: proactivePreferences.travel_buffer_minutes ?? 15,
          }, language)} 〉</Text>
        </View>
      </Picker>
      <View className='switch-row'>
        <Text>{translate('quietHours', {}, language)}</Text>
        <Switch
          checked={Boolean(proactivePreferences.quiet_hours?.enabled)}
          disabled={!proactiveEnabled || Boolean(saving)}
          color='#e88240'
          onChange={(event) => void updateProactive('proactive-quiet', {
            quiet_hours: {
              ...(proactivePreferences.quiet_hours || {}),
              enabled: event.detail.value,
            },
          })}
        />
      </View>
      <View className='motto-heading'>
        <View>
          <Text className='motto-title'>{translate('fallbackMottos', {}, language)}</Text>
          <Text className='section-hint'>{translate('fallbackHint', {}, language)}</Text>
        </View>
        <Text className='motto-count'>{mottos.length}/5</Text>
      </View>
      <View className='motto-list'>
        {mottos.map((motto, index) => <View className='motto-row' key={index}>
          <Input
            value={motto}
            maxlength={80}
            disabled={Boolean(saving)}
            placeholder={translate('mottoPlaceholder', {}, language)}
            onInput={(event) => setMottos((items) => items.map((item, itemIndex) => (
              itemIndex === index ? event.detail.value : item
            )))}
          />
          <Button disabled={Boolean(saving)}
            onClick={() => setMottos((items) => items.filter((_, itemIndex) => itemIndex !== index))}>×</Button>
        </View>)}
      </View>
      <View className='motto-actions'>
        <Button disabled={!proactiveEnabled || Boolean(saving) || mottos.length >= 5}
          onClick={() => setMottos((items) => [...items, ''])}>{translate('addMotto', {}, language)}</Button>
        <Button disabled={!proactiveEnabled || Boolean(saving)}
          onClick={() => void updateProactive('proactive-mottos', {
            fallback_mottos: mottos.map((item) => item.trim()).filter(Boolean).slice(0, 5),
          })}>{translate('saveMottos', {}, language)}</Button>
        <Button loading={saving === 'proactive-refresh'} disabled={!proactiveEnabled || Boolean(saving)}
          onClick={() => void refreshProactive()}>{translate('checkNow', {}, language)}</Button>
      </View>
    </View>

    <View className='setting-section danger-section'>
      <Text className='section-title'>{translate('dataManagement', {}, language)}</Text>
      <Text className='section-hint'>{translate('dataClearHint', {}, language)}</Text>
      {!resetVisible ? <Button className='danger-outline' onClick={() => {
        setResetPassword('')
        setResetVisible(true)
      }}>{translate('clearDatabase', {}, language)}</Button> : <View className='reset-editor'>
        <Text>{translate('dataClearWarningTitle', {}, language)}</Text>
        <Text>{translate('dataClearWarningBody', {}, language)}</Text>
        <Input
          password
          value={resetPassword}
          disabled={saving === 'reset'}
          placeholder={translate('dataClearPasswordPlaceholder', {}, language)}
          onInput={(event) => setResetPassword(event.detail.value)}
        />
        <View>
          <Button disabled={saving === 'reset'} onClick={() => setResetVisible(false)}>
            {translate('cancel', {}, language)}
          </Button>
          <Button
            className='danger'
            loading={saving === 'reset'}
            disabled={!resetPassword || saving === 'reset'}
            onClick={() => void clearData()}
          >{translate('confirmClearDatabase', {}, language)}</Button>
        </View>
      </View>}
    </View>

    <View className='account-note'>
      <Text>{translate('wechatIdentity', { id: session?.userId.slice(-8) || '' }, language)}</Text>
      <Text>{translate('makersStorageNote', {}, language)}</Text>
    </View>
  </View>
}
