import { useEffect, useRef, useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Image, ScrollView, Text, Textarea, View } from '@tarojs/components'
import {
  createChatPayload,
  createClarificationPayload,
  createLocationRetryPayload,
  mergeMessages,
  restoredConversationWasInterrupted,
  settleStoppedMessages,
  type ChatMessage,
  type ChatRequestPayload,
  type WorkspaceAction,
} from '@floris/contracts'
import MessageBubble from '@/components/MessageBubble'
import type { WorkspaceOperation } from '@/components/WorkspaceActionCard'
import {
  normalizeLanguage,
  translate,
  type Language,
  type TranslationKey,
} from '@/i18n'
import {
  applyClarificationPatch,
  startChatStream,
  stopMakerRun,
  type ActiveChatStream,
} from '@/services/chat'
import {
  conversationRunActive,
  recoverConversation,
  recoveringMessages,
} from '@/services/conversation-recovery'
import {
  bootstrap,
  cacheMessages,
  getOrCreateConversationId,
  listConversations,
  newConversation,
  readCachedMessages,
  setActiveConversationId,
  type ConversationSummary,
} from '@/services/conversations'
import { requestCurrentLocation } from '@/services/location'
import { addPdfToReading, imageDataUrl, uploadToMakers } from '@/services/files'
import {
  proactiveOperation,
  proactiveTickerLines,
} from '@/services/proactive'
import { ensureSession, readSession } from '@/services/session'
import { workspaceOperation } from '@/services/workspace'
import { updateNativeTabBar } from '@/services/tabbar'
import florisAvatar from '@/assets/floris/avatar.png'
import florisChatLight from '@/assets/floris/chat-light.jpg'
import florisChatDark from '@/assets/floris/chat-dark.jpg'
import './index.scss'

const STATUS_COPY: Record<string, [TranslationKey, TranslationKey]> = {
  rich_search: ['statusSearchActive', 'statusSearchDone'],
  search_places: ['statusPlacesActive', 'statusPlacesDone'],
  search_places_batch: ['statusPlacesActive', 'statusPlacesDone'],
  plan_route_between_places: ['statusRouteActive', 'statusRouteDone'],
  recommend_places_on_map: ['statusMapActive', 'statusMapDone'],
  recommend_nearby_places_on_map: ['statusNearbyActive', 'statusNearbyDone'],
  propose_calendar_changes: ['statusCalendarActive', 'statusCalendarDone'],
  propose_image: ['statusImageActive', 'statusImageDone'],
  image_generation_planning: ['statusImagePlanActive', 'statusImageDone'],
  search_arxiv: ['statusPaperActive', 'statusPaperDone'],
}

const PENDING_PROACTIVE_PROMPT_KEY = 'floris.miniapp.pending-proactive-prompt.v1'

function initialChatState(): {
  conversationId: string
  messages: ChatMessage[]
  ready: boolean
} {
  const session = readSession()
  if (!session) return { conversationId: '', messages: [], ready: false }
  const conversationId = getOrCreateConversationId(session)
  return {
    conversationId,
    messages: readCachedMessages(conversationId),
    ready: true,
  }
}

export default function IndexPage() {
  const [initial] = useState(initialChatState)
  const [ready, setReady] = useState(initial.ready)
  const [error, setError] = useState('')
  const [conversationId, setConversationId] = useState(initial.conversationId)
  const [messages, setMessages] = useState<ChatMessage[]>(initial.messages)
  const [recentConversations, setRecentConversations] = useState<ConversationSummary[]>([])
  const [draft, setDraft] = useState('')
  const [referenceImage, setReferenceImage] = useState<{ name: string; dataUrl: string } | null>(null)
  const [attaching, setAttaching] = useState(false)
  const [continuationPending, setContinuationPending] = useState(false)
  const [statusText, setStatusText] = useState('')
  const [actionBusy, setActionBusy] = useState('')
  const [tickerLines, setTickerLines] = useState<string[]>([])
  const [reminderIndex, setReminderIndex] = useState(0)
  const [language, setLanguage] = useState<Language>(() => normalizeLanguage(Taro.getStorageSync('floris-language')))
  const activeStream = useRef<ActiveChatStream | null>(null)
  const messagesRef = useRef<ChatMessage[]>(initial.messages)
  const streaming = messages.some((message) => message.streaming)
  const interactionLocked = !ready || streaming || continuationPending

  const publish = (updater: ChatMessage[] | ((current: ChatMessage[]) => ChatMessage[])) => {
    setMessages((current) => {
      const next = typeof updater === 'function' ? updater(current) : updater
      messagesRef.current = next
      return next
    })
  }

  const refreshReminders = async (
    operation: 'page_open' | 'get' | 'memory_refresh' = 'get',
    targetConversationId = conversationId,
  ) => {
    if (!targetConversationId) return
    try {
      const data = await proactiveOperation(targetConversationId, operation)
      setTickerLines(proactiveTickerLines(data))
      setReminderIndex(0)
    } catch {
      // Reminders never block chat.
    }
  }

  const ingestLocationSignal = async (
    location: {
      latitude: number
      longitude: number
      captured_at: number
    },
    targetConversationId = conversationId,
  ) => {
    if (!targetConversationId) return
    try {
      const state = await proactiveOperation(targetConversationId, 'ingest_signal', {
        signal_type: 'browser_location_weather',
        dedup_key: `miniapp-location:${Math.floor(location.captured_at / 3_600_000)}`,
        payload: {
          latitude: location.latitude,
          longitude: location.longitude,
        },
      })
      setTickerLines(proactiveTickerLines(state))
      setReminderIndex(0)
    } catch {
      // Location enrichment must never block chat.
    }
  }

  const refreshAuthorizedLocation = async (targetConversationId = conversationId) => {
    if (!targetConversationId) return
    const setting = await Taro.getSetting().catch(() => null)
    if (setting?.authSetting?.['scope.userLocation'] !== true) return
    const result = await requestCurrentLocation()
    if (result.location) await ingestLocationSignal(result.location, targetConversationId)
  }

  useEffect(() => {
    let disposed = false
    void (async () => {
      try {
        const session = await ensureSession()
        const id = getOrCreateConversationId(session)
        const cached = readCachedMessages(id)
        if (disposed) return
        setConversationId(id)
        publish((current) => current.length ? current : cached)
        // The cached session is enough for the native shell to become usable.
        // Durable Makers state is reconciled in the background so opening the
        // mini program is not gated by a full remote bootstrap.
        setReady(true)
        setTimeout(() => {
          void listConversations()
            .then((items) => {
              if (!disposed) setRecentConversations(items.slice(0, 6))
            })
            .catch(() => undefined)
        }, 0)
        const data = await bootstrap(id).catch(() => ({ messages: [], run: undefined }))
        if (disposed) return
        if (activeStream.current) {
          setTimeout(() => void refreshReminders('page_open', id), 0)
          setTimeout(() => void refreshAuthorizedLocation(id), 0)
          return
        }
        const runActive = conversationRunActive(data)
        const restored = Array.isArray(data.messages) ? data.messages : []
        const merged = mergeMessages(restored, cached)
        if (runActive) {
          let recoveryDetached = false
          const runId = String(data.run?.run_id || Date.now())
          const recoveryControl: ActiveChatStream = {
            async stop() {
              recoveryDetached = true
              await stopMakerRun(id).catch(() => undefined)
            },
            detach() {
              recoveryDetached = true
            },
          }
          activeStream.current = recoveryControl
          publish(recoveringMessages(merged, `recovering-${runId}`))
          setStatusText(translate('restoringAnswer', {}, language))

          const recovered = await recoverConversation(id, {
            initial: data,
            cancelled: () => disposed || recoveryDetached,
            onSnapshot(snapshot) {
              if (disposed || recoveryDetached) return
              const snapshotMessages = Array.isArray(snapshot.messages) ? snapshot.messages : []
              const next = mergeMessages(snapshotMessages, messagesRef.current, {
                preserveStreaming: conversationRunActive(snapshot),
              })
              if (conversationRunActive(snapshot)) {
                publish(recoveringMessages(next, `recovering-${runId}`))
              }
            },
          })
          if (disposed || recoveryDetached) return
          activeStream.current = null
          setStatusText('')
          const finalMessages = settleStoppedMessages(mergeMessages(
            Array.isArray(recovered.data.messages) ? recovered.data.messages : [],
            messagesRef.current,
          ))
          const interrupted = (
            recovered.timedOut
            || restoredConversationWasInterrupted(finalMessages, false)
          )
          if (recovered.timedOut) {
            await stopMakerRun(id).catch(() => undefined)
          }
          publish(interrupted
            ? [...finalMessages, {
              id: `interrupted-${runId}`,
              role: 'ai',
              content: translate(
                recovered.timedOut ? 'recoveryTimedOut' : 'previousInterrupted',
                {},
                language,
              ),
              ts: Date.now(),
              failed: true,
            }]
            : finalMessages)
        } else {
          const normalized = settleStoppedMessages(merged)
          const interrupted = restoredConversationWasInterrupted(normalized, false)
          publish(interrupted
            ? [...normalized, {
              id: `interrupted-${Date.now()}`,
              role: 'ai',
              content: translate('previousInterrupted', {}, language),
              ts: Date.now(),
              failed: true,
            }]
            : normalized)
        }
        setTimeout(() => void refreshReminders('page_open', id), 0)
        setTimeout(() => void refreshAuthorizedLocation(id), 0)
      } catch (reason) {
        if (!disposed) setError(String((reason as Error)?.message || reason))
      }
    })()
    return () => {
      disposed = true
      activeStream.current?.detach()
      activeStream.current = null
    }
    // Login/bootstrap only runs once for this page instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useDidShow(() => {
    const nextLanguage = normalizeLanguage(Taro.getStorageSync('floris-language'))
    setLanguage(nextLanguage)
    void updateNativeTabBar(nextLanguage)
    const pendingPrompt = String(Taro.getStorageSync(PENDING_PROACTIVE_PROMPT_KEY) || '')
    if (pendingPrompt && !streaming) {
      Taro.removeStorageSync(PENDING_PROACTIVE_PROMPT_KEY)
      setDraft(pendingPrompt)
    }
    if (ready) void refreshReminders('page_open')
    if (ready) void refreshAuthorizedLocation()
  })

  useEffect(() => {
    const update = interactionLocked ? Taro.hideTabBar : Taro.showTabBar
    void update({ animation: true }).catch(() => undefined)
  }, [interactionLocked])

  useEffect(() => {
    if (!ready || !conversationId) return
    const timer = setInterval(() => {
      void refreshReminders('memory_refresh', conversationId)
    }, 10 * 60 * 1000)
    return () => clearInterval(timer)
  }, [ready, conversationId])

  useEffect(() => {
    if (tickerLines.length < 2) return
    const timer = setInterval(() => {
      setReminderIndex((current) => (current + 1) % tickerLines.length)
    }, 6_000)
    return () => clearInterval(timer)
  }, [tickerLines.length])

  useEffect(() => {
    if (conversationId && messages.length && !messages.some((item) => item.streaming)) {
      cacheMessages(conversationId, messages)
    }
  }, [conversationId, messages])

  const patchMessage = (id: string, patcher: (message: ChatMessage) => ChatMessage) => {
    publish((current) => current.map((message) => message.id === id ? patcher(message) : message))
  }

  const runStream = async (payload: ChatRequestPayload, assistantId: string) => {
    if (!conversationId || activeStream.current) return
    setError('')
    patchMessage(assistantId, (message) => ({ ...message, streaming: true, failed: false }))
    try {
      activeStream.current = await startChatStream(conversationId, payload, {
        onPatch(patch) {
          if (patch.status) {
            const copy = STATUS_COPY[patch.status.name]
            const key = copy?.[patch.status.phase === 'active' ? 0 : 1]
            setStatusText(key ? translate(key, {}, language) : translate('statusProcessing', {}, language))
          }
          patchMessage(assistantId, (message) => {
            const next = { ...message }
            if (patch.reset) next.content = ''
            if (patch.delta) next.content += patch.delta
            if (patch.complete) next.streaming = false
            if (patch.error) {
              next.content = patch.error
              next.failed = true
              next.streaming = false
              if (next.clarification) next.clarificationAnswered = false
            }
            if (patch.searchResults) {
              next.searchResults = {
                ...(next.searchResults || {}),
                ...patch.searchResults,
                media: patch.searchResults.media?.length
                  ? patch.searchResults.media
                  : next.searchResults?.media,
              }
            }
            if (patch.workspaceAction) {
              next.workspaceActions = [
                ...(next.workspaceActions || []).filter((item) => item.id !== patch.workspaceAction?.id),
                patch.workspaceAction,
              ]
            }
            if (patch.clarification) {
              return applyClarificationPatch(next, patch.clarification)
            }
            if (patch.followUps?.length) next.followUps = patch.followUps
            if (patch.papers?.length) next.papers = patch.papers
            return next
          })
        },
        onError(message) {
          patchMessage(assistantId, (current) => ({
            ...current,
            content: message,
            failed: true,
            streaming: false,
            ...(current.clarification ? { clarificationAnswered: false } : {}),
          }))
        },
        onDone() {
          activeStream.current = null
          setStatusText('')
          patchMessage(assistantId, (message) => ({ ...message, streaming: false }))
        },
        onLocationRequired() {
          setContinuationPending(true)
          void requestCurrentLocation()
            .then(async ({ location, request }) => {
              if (location) {
                void ingestLocationSignal(location)
              }
              await runStream(createLocationRetryPayload(payload, location, request), assistantId)
            })
            .finally(() => setContinuationPending(false))
        },
      })
    } catch (reason) {
      activeStream.current = null
      patchMessage(assistantId, (message) => ({
        ...message,
        content: String((reason as Error)?.message || reason),
        failed: true,
        streaming: false,
        ...(message.clarification ? { clarificationAnswered: false } : {}),
      }))
    }
  }

  const sendText = async (text = draft) => {
    const content = text.trim()
    if (!content || streaming || activeStream.current || !ready) return
    const now = Date.now()
    const userMessage: ChatMessage = {
      id: `user-${now}`,
      role: 'user',
      content: referenceImage
        ? `${content}\n\n${translate('attachedReference', { name: referenceImage.name }, language)}`
        : content,
      ts: now,
    }
    const assistant: ChatMessage = {
      id: `assistant-${now}`,
      role: 'ai',
      content: '',
      ts: now + 1,
      streaming: true,
    }
    publish((current) => [...current, userMessage, assistant])
    setDraft('')
    const payload = createChatPayload(userMessage, language)
    payload.reference_images = referenceImage ? [referenceImage.dataUrl] : []
    setReferenceImage(null)
    await runStream(payload, assistant.id)
  }

  const attach = async () => {
    if (streaming || attaching) return
    const selection = await Taro.showActionSheet({
      itemList: [
        translate('chooseReferenceImage', {}, language),
        translate('uploadPdfReading', {}, language),
      ],
    }).catch(() => null)
    if (!selection) return
    setAttaching(true)
    try {
      if (selection.tapIndex === 0) {
        const picked = await Taro.chooseMedia({ count: 1, mediaType: ['image'], sourceType: ['album', 'camera'] })
        const file = picked.tempFiles[0]
        if (!file) return
        setReferenceImage({
          name: file.tempFilePath.split('/').pop() || translate('referenceImage', {}, language),
          dataUrl: await imageDataUrl(file.tempFilePath),
        })
        return
      }
      const picked = await Taro.chooseMessageFile({
        count: 1,
        type: 'file',
        extension: ['pdf'],
      })
      const file = picked.tempFiles[0]
      if (!file) return
      const uploaded = await uploadToMakers(
        conversationId,
        file.path,
        file.name,
        'application/pdf',
        file.size,
      )
      await addPdfToReading(uploaded)
      void proactiveOperation(conversationId, 'ingest_signal', {
        signal_type: 'file_uploaded',
        dedup_key: uploaded.storageKey,
        payload: {
          file_id: uploaded.storageKey,
          storage_key: uploaded.storageKey,
          filename: uploaded.name,
          mime_type: uploaded.mimeType,
          is_paper: false,
          ui_language: language,
        },
      }).then((state) => {
        setTickerLines(proactiveTickerLines(state))
        setReminderIndex(0)
      }).catch(() => undefined)
      void Taro.showToast({ title: translate('addedToReading', {}, language), icon: 'success' })
    } catch (reason) {
      void Taro.showToast({ title: String((reason as Error)?.message || translate('addFailed', {}, language)), icon: 'none' })
    } finally {
      setAttaching(false)
    }
  }

  const submitClarification = (message: ChatMessage, values: Record<string, string | string[]>) => {
    if (!message.clarification || streaming) return
    patchMessage(message.id, (current) => ({ ...current, clarificationAnswered: true }))
    void runStream(
      createClarificationPayload(message.clarification, values, message.id, language),
      message.id,
    )
  }

  const executeAction = async (
    action: WorkspaceAction,
    operation: WorkspaceOperation,
    input: Record<string, unknown> = {},
  ) => {
    if (actionBusy) return
    setActionBusy(action.id)
    try {
      const result = await workspaceOperation(conversationId, operation, {
        action_id: action.id,
        version: action.version,
        ...input,
      })
      if (result.action) {
        publish((current) => current.map((message) => ({
          ...message,
          workspaceActions: message.workspaceActions?.map((item) => item.id === action.id ? result.action! : item),
        })))
      }
      if (operation === 'activate_map') {
        const map = result.map || {
          action_id: action.id,
          title: String(action.payload.title || translate('relatedPlaces', {}, language)),
          places: Array.isArray(action.payload.places) ? action.payload.places as Array<Record<string, unknown>> : [],
          route_mode: String(action.payload.route_mode || ''),
          route_strategy: String(action.payload.route_strategy || ''),
          show_route: Boolean(action.payload.show_route),
        }
        Taro.setStorageSync('floris.miniapp.active-map.v1', map)
        await Taro.navigateTo({ url: '/pages/map/index' })
      }
      void refreshReminders('get')
    } catch (reason) {
      void Taro.showToast({ title: String((reason as Error)?.message || translate('operationFailed', {}, language)), icon: 'none' })
    } finally {
      setActionBusy('')
    }
  }

  const stop = async () => {
    const stream = activeStream.current
    activeStream.current = null
    setStatusText('')
    publish((current) => current
      .filter((message) => !message.streaming || Boolean(message.content || message.clarification || message.workspaceActions?.length))
      .map((message) => ({ ...message, streaming: false })))
    // Restore the composer immediately. The durable Makers cancellation can
    // finish in parallel; the next deliberate send observes its pending
    // marker and will not start another graph writer prematurely.
    if (stream) await stream.stop()
  }

  const createNew = async () => {
    if (streaming) return
    const session = await ensureSession()
    const id = newConversation(session)
    setConversationId(id)
    publish([])
  }

  const openConversation = async (id: string) => {
    if (interactionLocked || id === conversationId) return
    setActiveConversationId(id)
    await Taro.reLaunch({ url: '/pages/index/index' })
  }

  const retry = (failed: ChatMessage) => {
    const index = messagesRef.current.findIndex((message) => message.id === failed.id)
    const previousUser = [...messagesRef.current.slice(0, index)].reverse()
      .find((message) => message.role === 'user')
    if (previousUser) void sendText(previousUser.content)
  }

  const reminderText = tickerLines[reminderIndex] || ''
  const starters = [
    { icon: '⌁', label: translate('suggestionNews', {}, language) },
    { icon: '◷', label: translate('suggestionTrip', {}, language) },
    { icon: '✦', label: translate('suggestionCat', {}, language) },
  ]

  if (error && !ready) {
    return <View className='center-state'>
      <Image className='state-avatar' src={florisAvatar} />
      <Text>{error}</Text>
      <Button className='primary-button' onClick={() => Taro.reLaunch({ url: '/pages/index/index' })}>{translate('loginAgain', {}, language)}</Button>
    </View>
  }

  return <View
    className='chat-page'
    style={`--floris-chat-light:url(${florisChatLight});--floris-chat-dark:url(${florisChatDark})`}
  >
    <View className='chat-layout'>
      <View className='chat-side-panel'>
        <View className='side-brand'>
          <Image className='side-avatar' src={florisAvatar} />
          <View className='side-brand-copy'>
            <Text className='side-brand-name'>FLORIS</Text>
            <Text className='side-brand-note'>{translate('emptyChatGreeting', {}, language)}</Text>
          </View>
        </View>
        <View
          className={`side-reminder ${interactionLocked ? 'is-disabled' : ''}`}
          role='button'
          aria-label={translate('openProactive', {}, language)}
          hoverClass='floris-card-press'
          hoverStayTime={80}
          onClick={() => {
            if (!interactionLocked) void Taro.switchTab({ url: '/pages/proactive/index' })
          }}
        >
          <Text className='side-reminder-spark'>✦</Text>
          <Text key={reminderIndex} className='side-reminder-copy'>
            {reminderText || translate('gentleReminderFallback', {}, language)}
          </Text>
        </View>
        <Button
          className='side-new-conversation'
          aria-label={translate('createConversation', {}, language)}
          disabled={interactionLocked}
          onClick={createNew}
        >
          <Text>＋</Text>
          <Text>{translate('createConversation', {}, language)}</Text>
        </Button>
        <View
          className='side-section-heading'
          role='button'
          aria-label={translate('openHistory', {}, language)}
          hoverClass='floris-press'
          hoverStayTime={80}
          onClick={() => {
            if (!interactionLocked) void Taro.navigateTo({ url: '/pages/history/index' })
          }}
        >
          <Text>{translate('openHistory', {}, language)}</Text>
          <Text>◴</Text>
        </View>
        <ScrollView className='side-conversation-list' scrollY showScrollbar={false}>
          {recentConversations.map((item) => <View
            key={item.id}
            className={`side-conversation ${item.id === conversationId ? 'is-active' : ''}`}
            hoverClass='floris-press'
            hoverStayTime={80}
            onClick={() => void openConversation(item.id)}
          >
            <Text className='side-conversation-title'>{item.title}</Text>
            <Text className='side-conversation-meta'>
              {translate('messageCount', { count: item.messageCount }, language)}
            </Text>
          </View>)}
          {!recentConversations.length ? <View className='side-conversation-skeleton'>
            <View />
            <View />
            <View />
          </View> : null}
        </ScrollView>
      </View>

      <View className='chat-main'>
        <View className='chat-context-bar'>
          <View
            className={`reminder-ticker ${interactionLocked ? 'is-disabled' : ''}`}
            role='button'
            hoverClass='floris-press'
            hoverStayTime={80}
            aria-label={translate('openProactive', {}, language)}
            onClick={() => {
              if (!interactionLocked) void Taro.switchTab({ url: '/pages/proactive/index' })
            }}
          >
            <Text className='reminder-spark'>✦</Text>
            <Text key={reminderIndex} className='reminder-copy ticker-copy-enter'>
              {reminderText || translate('gentleReminderFallback', {}, language)}
            </Text>
            <Text className='reminder-arrow'>›</Text>
          </View>
        </View>
        <View className='conversation-toolbar'>
          <Button disabled={interactionLocked} onClick={createNew}>
            <Text className='toolbar-icon'>＋</Text>
            <Text className='toolbar-label'>{translate('createConversation', {}, language)}</Text>
          </Button>
          <Button disabled={interactionLocked} onClick={() => Taro.navigateTo({ url: '/pages/history/index' })}>
            <Text className='toolbar-icon'>◴</Text>
            <Text className='toolbar-label'>{translate('openHistory', {}, language)}</Text>
          </Button>
        </View>

        <ScrollView
          className='message-list'
          scrollY
          scrollIntoView='chat-bottom-anchor'
          enhanced
          showScrollbar={false}
        >
          {!ready ? <View className='chat-loading'>
            <View className='loading-avatar' />
            <View className='loading-copy loading-copy-wide' />
            <View className='loading-copy' />
            <View className='loading-card-row'>
              <View />
              <View />
            </View>
          </View> : null}
          {!messages.length && ready ? <View className='empty-chat'>
            <View className='empty-avatar-halo'>
              <Image className='empty-avatar' src={florisAvatar} />
            </View>
            <Text className='empty-kicker'>{translate('emptyChatGreeting', {}, language)}</Text>
            <Text className='empty-title'>{translate('emptyChatTitle', {}, language)}</Text>
            <Text className='empty-subtitle'>{translate('emptyChatSubtitle', {}, language)}</Text>
            <Text className='starter-heading'>{translate('quickStart', {}, language)}</Text>
            <View className='starter-grid'>
              {starters.map((item, index) =>
                <View key={item.label} className={`suggestion suggestion-${index}`} hoverClass='floris-card-press'
                  hoverStayTime={80} onClick={() => void sendText(item.label)}>
                  <Text className='suggestion-icon'>{item.icon}</Text>
                  <Text>{item.label}</Text>
                  <Text className='suggestion-arrow'>↗</Text>
                </View>)}
            </View>
          </View> : null}
          {messages.map((message) => <MessageBubble
            key={message.id}
            message={message}
            statusText={message.streaming ? statusText : ''}
            actionBusy={actionBusy}
            onClarification={submitClarification}
            onAction={executeAction}
            onFollowUp={(value) => void sendText(value)}
            onRetry={retry}
          />)}
          <View id='chat-bottom-anchor' className='bottom-anchor' />
        </ScrollView>

        <View className='composer'>
          {referenceImage ? <View className='reference-chip'>
            <Image src={referenceImage.dataUrl} mode='aspectFill' />
            <Text>{referenceImage.name}</Text>
            <Text aria-label={translate('removeReference', {}, language)}
              onClick={() => {
                if (!interactionLocked) setReferenceImage(null)
              }}>×</Text>
          </View> : null}
          <View className='composer-shell'>
            <Button className='attach-button' aria-label={translate('addAttachment', {}, language)} loading={attaching} disabled={interactionLocked} onClick={() => void attach()}>＋</Button>
            <Textarea
              className='composer-input'
              disabled={interactionLocked}
              maxlength={4000}
              placeholder={ready
                ? translate('chatPlaceholder', {}, language)
                : translate('enteringHome', {}, language)}
              value={draft}
              onInput={(event) => setDraft(event.detail.value)}
              onConfirm={() => void sendText()}
              confirmType='send'
              showConfirmBar={false}
            />
            {streaming
              ? <Button className='send-button stop-button' aria-label={translate('stopGeneration', {}, language)} onClick={() => void stop()}>■</Button>
              : <Button className='send-button' aria-label={translate('sendMessage', {}, language)} disabled={!draft.trim() || interactionLocked} onClick={() => void sendText()}>↑</Button>}
          </View>
        </View>
      </View>
    </View>
  </View>
}
