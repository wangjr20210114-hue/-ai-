import { useEffect, useRef, useState } from 'react'
import Taro from '@tarojs/taro'
import { Button, Input, ScrollView, Text, Textarea, View } from '@tarojs/components'
import MarkdownMessage from '@/components/MarkdownMessage'
import { getOrCreateConversationId } from '@/services/conversations'
import { apiRequest } from '@/services/request'
import { startReaderStream, type ReaderAction } from '@/services/reader'
import { ensureSession } from '@/services/session'
import type { ChunkedSseTask } from '@/services/stream'
import './index.scss'

type AssistantResult = {
  id: string
  action: ReaderAction
  title: string
  source_text: string
  content: string
  created_at: number
}

const actionLabels: Array<[ReaderAction, string]> = [
  ['translate', '翻译'],
  ['summarize', '总结'],
  ['explain', '解释'],
  ['formula', '公式'],
  ['terms', '术语'],
  ['analyze', '分析'],
  ['qa', '问答'],
]

export default function ReaderPage() {
  const [conversationId, setConversationId] = useState('')
  const [storageKey] = useState(String(Taro.getStorageSync('floris.miniapp.reader-file.v1') || ''))
  const [text, setText] = useState('')
  const [question, setQuestion] = useState('')
  const [action, setAction] = useState<ReaderAction>('translate')
  const [output, setOutput] = useState('')
  const [history, setHistory] = useState<AssistantResult[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const taskRef = useRef<ChunkedSseTask | null>(null)
  const outputRef = useRef('')
  const language = String(Taro.getStorageSync('floris-language') || 'zh-CN')

  useEffect(() => {
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
    outputRef.current = ''
    let completed = false
    const done = async () => {
      if (completed) return
      completed = true
      taskRef.current = null
      setRunning(false)
      const content = outputRef.current.trim()
      if (!content || !storageKey) return
      try {
        const saved = await apiRequest<{ result?: AssistantResult }>('/library', {
          method: 'POST',
          data: {
            operation: 'save_assistant_result',
            storage_key: storageKey,
            action,
            title: actionLabels.find(([id]) => id === action)?.[1] || '助读结果',
            source_text: text.slice(0, 4000),
            content,
          },
        })
        if (saved.result) setHistory((items) => [saved.result!, ...items.filter((item) => item.id !== saved.result?.id)])
      } catch {
        void Taro.showToast({ title: '结果已生成，但保存失败', icon: 'none' })
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
        onDone() { void done() },
        onError(value) {
          setError(value)
          void done()
        },
      },
    )
  }

  const stop = () => {
    taskRef.current?.abort()
    taskRef.current = null
    setRunning(false)
  }

  return <View className='reader-page'>
    <View className='reader-toolbar'>
      {actionLabels.map(([id, label]) => <View key={id} className={`reader-action ${action === id ? 'active' : ''}`} onClick={() => !running && setAction(id)}>{label}</View>)}
    </View>
    <View className='source-panel'>
      <View className='source-header'><Text>论文文本</Text><Button onClick={() => void paste()}>粘贴剪贴板</Button></View>
      <Textarea
        className='source-input'
        disabled={running}
        maxlength={120000}
        placeholder='在微信原生 PDF 预览中复制要处理的段落，然后粘贴到这里。'
        value={text}
        onInput={(event) => setText(event.detail.value)}
      />
      {action === 'qa' ? <Input className='question-input' disabled={running} placeholder='输入仅依据这段论文文本回答的问题'
        value={question} onInput={(event) => setQuestion(event.detail.value)} /> : null}
      {running
        ? <Button className='stop-reader' onClick={stop}>停止</Button>
        : <Button className='run-reader' disabled={!text.trim() || (action === 'qa' && !question.trim())} onClick={() => void run()}>开始{actionLabels.find(([id]) => id === action)?.[1]}</Button>}
    </View>
    <ScrollView className='reader-results' scrollY>
      {output || running || error ? <View className='latest-result'>
        <Text className='result-label'>最新结果 · 流式输出</Text>
        {output ? <MarkdownMessage content={output} /> : null}
        {running && !output ? <Text>正在阅读这段内容…</Text> : null}
        {error ? <Text className='reader-error'>{error}</Text> : null}
      </View> : null}
      {history.map((item) => <View className='history-result' key={item.id}>
        <Text className='result-label'>{item.title} · {new Date(item.created_at).toLocaleString()}</Text>
        <MarkdownMessage content={item.content} />
      </View>)}
    </ScrollView>
  </View>
}
