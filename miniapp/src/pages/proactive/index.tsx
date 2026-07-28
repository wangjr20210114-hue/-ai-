import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Button, Text, View } from '@tarojs/components'
import { getOrCreateConversationId } from '@/services/conversations'
import {
  actionableProactiveWorkflows,
  activeProactiveNotifications,
  currentWorkflowStep,
  proactiveOperation,
  type ProactiveNotification,
  type ProactiveWorkflow,
  type ProactiveWorkflowStep,
} from '@/services/proactive'
import { ensureSession } from '@/services/session'
import './index.scss'

const PENDING_PROMPT_KEY = 'floris.miniapp.pending-proactive-prompt.v1'

export default function ProactivePage() {
  const [conversationId, setConversationId] = useState('')
  const [notifications, setNotifications] = useState<ProactiveNotification[]>([])
  const [workflows, setWorkflows] = useState<ProactiveWorkflow[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')

  const load = async (refresh = false) => {
    setLoading(true)
    try {
      const session = await ensureSession()
      const id = getOrCreateConversationId(session)
      setConversationId(id)
      const state = await proactiveOperation(id, refresh ? 'refresh' : 'get')
      setNotifications(activeProactiveNotifications(state.notifications || []))
      setWorkflows(actionableProactiveWorkflows(state.workflows || []))
    } catch (reason) {
      void Taro.showToast({ title: String((reason as Error)?.message || '提醒读取失败'), icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  useDidShow(() => { void load(false) })

  const mutate = async (
    item: ProactiveNotification,
    operation: 'mark_read' | 'snooze' | 'dismiss',
  ) => {
    if (!conversationId || busy) return
    setBusy(item.id)
    try {
      const state = await proactiveOperation(conversationId, operation, {
        notification_id: item.id,
        ...(operation === 'snooze'
          ? { until: Math.floor(Date.now() / 1000) + 3600 }
          : {}),
      })
      setNotifications(activeProactiveNotifications(state.notifications || []))
      setWorkflows(actionableProactiveWorkflows(state.workflows || []))
      if (operation === 'mark_read' && item.action_prompt) {
        Taro.setStorageSync(PENDING_PROMPT_KEY, item.action_prompt)
        await Taro.navigateBack()
      }
    } catch (reason) {
      void Taro.showToast({ title: String((reason as Error)?.message || '操作失败'), icon: 'none' })
    } finally {
      setBusy('')
    }
  }

  const mutateWorkflow = async (
    operation:
      | 'confirm_workflow' | 'reject_workflow' | 'cancel_workflow'
      | 'complete_workflow_step' | 'skip_workflow_step' | 'fail_workflow_step'
      | 'retry_workflow_step' | 'compensate_workflow_step',
    workflow: ProactiveWorkflow,
    step?: ProactiveWorkflowStep,
  ) => {
    if (!conversationId || busy) return
    const key = `${operation}:${step?.id || workflow.id}`
    setBusy(key)
    try {
      const state = await proactiveOperation(conversationId, operation, {
        workflow_id: workflow.id,
        version: workflow.version,
        ...(step ? { step_id: step.id } : {}),
      })
      setNotifications(activeProactiveNotifications(state.notifications || []))
      setWorkflows(actionableProactiveWorkflows(state.workflows || []))
    } catch (reason) {
      void Taro.showToast({ title: String((reason as Error)?.message || '任务更新失败'), icon: 'none' })
    } finally {
      setBusy('')
    }
  }

  return <View className='proactive-page'>
    <View className='proactive-toolbar'>
      <Text>Floris 为你留意到</Text>
      <Button loading={loading} disabled={Boolean(busy)} onClick={() => void load(true)}>刷新</Button>
    </View>
    {!loading && !notifications.length && !workflows.length
      ? <Text className='proactive-empty'>目前没有需要打扰你的事。有可靠的新机会时，Floris 会在这里提醒。</Text>
      : null}
    {workflows.map((workflow) => {
      const step = currentWorkflowStep(workflow)
      return <View className='workflow-item' key={workflow.id}>
        <Text className='workflow-eyebrow'>{workflow.status === 'awaiting_confirmation' ? '主动服务提案' : '正在进行'}</Text>
        <Text className='proactive-title'>{workflow.title}</Text>
        {workflow.reason ? <Text className='proactive-body'>{workflow.reason}</Text> : null}
        {workflow.status === 'awaiting_confirmation'
          ? <View className='proactive-actions'>
            <Button className='proactive-handle' disabled={Boolean(busy)}
              onClick={() => void mutateWorkflow('confirm_workflow', workflow)}>开始</Button>
            <Button className='proactive-ignore' disabled={Boolean(busy)}
              onClick={() => void mutateWorkflow('reject_workflow', workflow)}>暂不需要</Button>
          </View>
          : <>
            {step ? <View className='workflow-step'>
              <Text className='workflow-step-title'>{step.title || '下一步'}</Text>
              {step.body ? <Text className='workflow-step-body'>{step.body}</Text> : null}
              {step.due_at ? <Text className='proactive-time'>计划时间：{new Date(step.due_at * 1000).toLocaleString()}</Text> : null}
              {step.last_error ? <Text className='workflow-error'>{step.last_error}</Text> : null}
            </View> : null}
            <View className='workflow-actions'>
              {step && ['pending', 'notified'].includes(step.status) ? <>
                <Button disabled={Boolean(busy)}
                  onClick={() => void mutateWorkflow('complete_workflow_step', workflow, step)}>已完成</Button>
                <Button disabled={Boolean(busy)}
                  onClick={() => void mutateWorkflow('skip_workflow_step', workflow, step)}>跳过</Button>
                <Button disabled={Boolean(busy)}
                  onClick={() => void mutateWorkflow('fail_workflow_step', workflow, step)}>遇到问题</Button>
              </> : null}
              {step?.status === 'compensating'
                ? <Button disabled={Boolean(busy)}
                  onClick={() => void mutateWorkflow('compensate_workflow_step', workflow, step)}>补救已完成</Button>
                : null}
              {step && ['failed', 'attention_required'].includes(step.status)
                ? <Button disabled={Boolean(busy)}
                  onClick={() => void mutateWorkflow('retry_workflow_step', workflow, step)}>重试这一步</Button>
                : null}
              <Button className='workflow-cancel' disabled={Boolean(busy)}
                onClick={() => void mutateWorkflow('cancel_workflow', workflow)}>停止任务</Button>
            </View>
          </>}
      </View>
    })}
    {notifications.map((item) => <View className={`proactive-item priority-${item.priority || 'normal'}`} key={item.id}>
      <Text className='proactive-title'>{item.title || '一条温柔提醒'}</Text>
      <Text className='proactive-body'>{item.body || ''}</Text>
      {item.status === 'snoozed' && item.snoozed_until
        ? <Text className='proactive-time'>稍后提醒：{new Date(item.snoozed_until * 1000).toLocaleString()}</Text>
        : null}
      <View className='proactive-actions'>
        <Button className='proactive-handle' disabled={Boolean(busy)} onClick={() => void mutate(item, 'mark_read')}>处理建议</Button>
        <Button className='proactive-later' disabled={Boolean(busy)} onClick={() => void mutate(item, 'snooze')}>一小时后</Button>
        <Button className='proactive-ignore' disabled={Boolean(busy)} onClick={() => void mutate(item, 'dismiss')}>忽略</Button>
      </View>
    </View>)}
  </View>
}
