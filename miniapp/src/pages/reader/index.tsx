import { useEffect, useRef, useState } from 'react'
import Taro from '@tarojs/taro'
import { Button, Input, ScrollView, Text, Textarea, View } from '@tarojs/components'
import MarkdownMessage from '@/components/MarkdownMessage'
import { getOrCreateConversationId } from '@/services/conversations'
import { apiRequest } from '@/services/request'
import { startReaderStream, type ReaderAction } from '@/services/reader'
import { ensureSession } from '@/services/session'
import type { ChunkedSseTask } from '@/services/stream'
import {
  localeFor,
  readLanguage,
  translate,
  type Language,
  type TranslationKey,
} from '@/i18n'
import './index.scss'

type AssistantResult = {
  id: string
  action: ReaderAction
  title: string
  source_text: string
  content: string
  created_at: number
}

const actionLabelKeys: Array<[ReaderAction, TranslationKey]> = [
  ['translate', 'readerTranslate'],
  ['summarize', 'readerSummarize'],
  ['explain', 'readerExplain'],
  ['formula', 'readerFormula'],
  ['terms', 'readerTerms'],
  ['analyze', 'readerAnalyze'],
  ['qa', 'readerQa'],
]

export default function ReaderPage() {
  const [conversationId, setConversationId] = useState('')
  const [storageKey] = useState(String(Taro.getStorageSync('floris.miniapp.reader-file.v1') || ''))
  const [text, setText] = useState('')
  const [question, setQuestion] = useState('')
  const [action, setAction] = useState<ReaderAction>('translate')
  const [output, setOutput] = useState('')
  const [history, setHistory] = useState<AssistantResult[]>([])
  const [latestSavedId, setLatestSavedId] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const taskRef = useRef<ChunkedSseTask | null>(null)
  const outputRef = useRef('')
  const stopRequestedRef = useRef(false)
  const [language] = useState<Language>(readLanguage())
  const actionLabel = (value: ReaderAction) => translate(
    actionLabelKeys.find(([id]) => id === value)?.[1] || 'readerResult',
    {},
    language,
  )

  useEffect(() => {
    void Taro.setNavigationBarTitle({ title: translate('navReader', {}, language) })
    void ensureSession().then((session) => setConversationId(getOrCreateConversationId(session)))
    if (!storageKey) return
    void apiRequest<{ items?: Array<{ storage_key?: string; assistant_results?: AssistantResult[] }> }>('/library')
      .then((result) => {
        const item = (result.items || []).find((candidate) => candidate.storage_key === storageKey)
        setHistory([...(item?.assistant_results || [])].sort((a, b) => Number(b.created_at) - Number(a.created_at)))
      })
      .catch(() => undefined)
    return () => taskRef.current?.abort()
  }, [storageKey])

  const paste = async () => {
    const clipboard = await Taro.getClipboardData()
    if (clipboard.data) setText(String(clipboard.data))
  }

  const run = async () => {
    if (!conversationId || !text.trim() || running || (action === 'qa' && !question.trim())) return
    setRunning(true)
    setError('')
    setOutput('')
    setLatestSavedId('')
    outputRef.current = ''
    stopRequestedRef.current = false
    let completed = false
    const done = async (persist: boolean) => {
      if (completed) return
      completed = true
      taskRef.current = null
      setRunning(false)
      const content = outputRef.current.trim()
      if (!persist || !content || !storageKey) return
      try {
        const saved = await apiRequest<{ result?: AssistantResult }>('/library', {
          method: 'POST',
          data: {
            operation: 'save_assistant_result',
            storage_key: storageKey,
            action,
            title: actionLabel(action),
            source_text: text.slice(0, 4000),
            content,
          },
        })
        if (saved.result) {
          setLatestSavedId(saved.result.id)
          setHistory((items) => [saved.result!, ...items.filter((item) => item.id !== saved.result?.id)])
        }
      } catch {
        void Taro.showToast({ title: translate('resultSaveFailed', {}, language), icon: 'none' })
      }
    }
    taskRef.current = await startReaderStream(
      conversationId,
      action,
      text.trim(),
      question.trim(),
      language,
      {
        onDelta(value) {
          outputRef.current += value
          setOutput(outputRef.current)
        },
        onDone() { void done(!stopRequestedRef.current) },
        onError(value) {
          setError(value)
          void done(false)
        },
      },
    )
  }

  const stop = () => {
    stopRequestedRef.current = true
    taskRef.current?.abort()
    taskRef.current = null
    setRunning(false)
  }

  return <View className='reader-page'>
    <View className='reader-hero'>
      <Text className='reader-kicker'>{translate('navReader', {}, language)}</Text>
      <Text className='reader-title'>{translate('readerOverview', {}, language)}</Text>
    </View>
    <View className='reader-toolbar'>
      {actionLabelKeys.map(([id]) => <View
        key={id}
        className={`reader-action ${action === id ? 'active' : ''}`}
        hoverClass='floris-press'
        hoverStayTime={80}
        onClick={() => !running && setAction(id)}
      >{actionLabel(id)}</View>)}
    </View>
    <View className='source-panel'>
      <View className='source-header'><Text>{translate('paperText', {}, language)}</Text><Button onClick={() => void paste()}>{translate('pasteClipboard', {}, language)}</Button></View>
      <Textarea
        className='source-input'
        disabled={running}
        maxlength={120000}
        placeholder={translate('readerSourcePlaceholder', {}, language)}
        value={text}
        onInput={(event) => setText(event.detail.value)}
      />
      {action === 'qa' ? <Input className='question-input' disabled={running} placeholder={translate('readerQuestionPlaceholder', {}, language)}
        value={question} onInput={(event) => setQuestion(event.detail.value)} /> : null}
      {running
        ? <Button className='stop-reader' onClick={stop}>{translate('stop', {}, language)}</Button>
        : <Button className='run-reader' disabled={!text.trim() || (action === 'qa' && !question.trim())} onClick={() => void run()}>{translate('startAction', { action: actionLabel(action) }, language)}</Button>}
    </View>
    <ScrollView className='reader-results' scrollY>
      {output || running || error ? <View className='latest-result'>
        <Text className='result-label'>{translate('latestStreaming', {}, language)}</Text>
        {output ? <MarkdownMessage content={output} /> : null}
        {running && !output ? <Text>{translate('readingNow', {}, language)}</Text> : null}
        {error ? <Text className='reader-error'>{error}</Text> : null}
      </View> : null}
      {history
        .filter((item) => !(output && item.id === latestSavedId))
        .map((item) => <View className='history-result' key={item.id}>
        <Text className='result-label'>{item.title} · {new Date(item.created_at).toLocaleString(localeFor(language))}</Text>
        <MarkdownMessage content={item.content} />
      </View>)}
    </ScrollView>
  </View>
}
