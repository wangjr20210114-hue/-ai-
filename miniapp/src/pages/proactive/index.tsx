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
import { localeFor, readLanguage, translate, type Language } from '@/i18n'
import { updateNativeTabBar } from '@/services/tabbar'
import './index.scss'

const PENDING_PROMPT_KEY = 'floris.miniapp.pending-proactive-prompt.v1'

export default function ProactivePage() {
  const [conversationId, setConversationId] = useState('')
  const [notifications, setNotifications] = useState<ProactiveNotification[]>([])
  const [workflows, setWorkflows] = useState<ProactiveWorkflow[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [language, setLanguage] = useState<Language>(readLanguage())

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
      void Taro.showToast({ title: String((reason as Error)?.message || translate('proactiveLoadFailed')), icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  useDidShow(() => {
    const nextLanguage = readLanguage()
    setLanguage(nextLanguage)
    void Taro.setNavigationBarTitle({ title: translate('navProactive', {}, nextLanguage) })
    void updateNativeTabBar(nextLanguage)
    void load(false)
  })

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
        await Taro.switchTab({ url: '/pages/index/index' })
      }
    } catch (reason) {
      void Taro.showToast({ title: String((reason as Error)?.message || translate('operationFailed')), icon: 'none' })
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
      void Taro.showToast({ title: String((reason as Error)?.message || translate('taskUpdateFailed')), icon: 'none' })
    } finally {
      setBusy('')
    }
  }

  return <View className='proactive-page'>
    <View className='proactive-toolbar'>
      <Text>{translate('proactiveHeading', {}, language)}</Text>
      <Button loading={loading} disabled={Boolean(busy)} onClick={() => void load(true)}>{translate('refresh', {}, language)}</Button>
    </View>
    {!loading && !notifications.length && !workflows.length
      ? <Text className='proactive-empty'>{translate('proactiveEmpty', {}, language)}</Text>
      : null}
    {workflows.map((workflow) => {
      const step = currentWorkflowStep(workflow)
      return <View className='workflow-item' key={workflow.id}>
        <Text className='workflow-eyebrow'>{translate(
          workflow.status === 'awaiting_confirmation' ? 'proactiveProposal' : 'inProgress',
          {},
          language,
        )}</Text>
        <Text className='proactive-title'>{workflow.title}</Text>
        {workflow.reason ? <Text className='proactive-body'>{workflow.reason}</Text> : null}
        {workflow.status === 'awaiting_confirmation'
          ? <View className='proactive-actions'>
            <Button className='proactive-handle' disabled={Boolean(busy)}
              onClick={() => void mutateWorkflow('confirm_workflow', workflow)}>{translate('start', {}, language)}</Button>
            <Button className='proactive-ignore' disabled={Boolean(busy)}
              onClick={() => void mutateWorkflow('reject_workflow', workflow)}>{translate('notNow', {}, language)}</Button>
          </View>
          : <>
            {step ? <View className='workflow-step'>
              <Text className='workflow-step-title'>{step.title || translate('nextStep', {}, language)}</Text>
              {step.body ? <Text className='workflow-step-body'>{step.body}</Text> : null}
              {step.due_at ? <Text className='proactive-time'>{translate('plannedTime', {
                time: new Date(step.due_at * 1000).toLocaleString(localeFor(language)),
              }, language)}</Text> : null}
              {step.last_error ? <Text className='workflow-error'>{step.last_error}</Text> : null}
            </View> : null}
            <View className='workflow-actions'>
              {step && ['pending', 'notified'].includes(step.status) ? <>
                <Button disabled={Boolean(busy)}
                  onClick={() => void mutateWorkflow('complete_workflow_step', workflow, step)}>{translate('done', {}, language)}</Button>
                <Button disabled={Boolean(busy)}
                  onClick={() => void mutateWorkflow('skip_workflow_step', workflow, step)}>{translate('skip', {}, language)}</Button>
                <Button disabled={Boolean(busy)}
                  onClick={() => void mutateWorkflow('fail_workflow_step', workflow, step)}>{translate('reportProblem', {}, language)}</Button>
              </> : null}
              {step?.status === 'compensating'
                ? <Button disabled={Boolean(busy)}
                  onClick={() => void mutateWorkflow('compensate_workflow_step', workflow, step)}>{translate('compensationDone', {}, language)}</Button>
                : null}
              {step && ['failed', 'attention_required'].includes(step.status)
                ? <Button disabled={Boolean(busy)}
                  onClick={() => void mutateWorkflow('retry_workflow_step', workflow, step)}>{translate('retryStep', {}, language)}</Button>
                : null}
              <Button className='workflow-cancel' disabled={Boolean(busy)}
                onClick={() => void mutateWorkflow('cancel_workflow', workflow)}>{translate('stopTask', {}, language)}</Button>
            </View>
          </>}
      </View>
    })}
    {notifications.map((item) => <View className={`proactive-item priority-${item.priority || 'normal'}`} key={item.id}>
      <Text className='proactive-title'>{item.title || translate('gentleReminder', {}, language)}</Text>
      <Text className='proactive-body'>{item.body || ''}</Text>
      {item.status === 'snoozed' && item.snoozed_until
        ? <Text className='proactive-time'>{translate('remindLater', {
          time: new Date(item.snoozed_until * 1000).toLocaleString(localeFor(language)),
        }, language)}</Text>
        : null}
      <View className='proactive-actions'>
        <Button className='proactive-handle' disabled={Boolean(busy)} onClick={() => void mutate(item, 'mark_read')}>{translate('handleSuggestion', {}, language)}</Button>
        <Button className='proactive-later' disabled={Boolean(busy)} onClick={() => void mutate(item, 'snooze')}>{translate('oneHourLater', {}, language)}</Button>
        <Button className='proactive-ignore' disabled={Boolean(busy)} onClick={() => void mutate(item, 'dismiss')}>{translate('ignore', {}, language)}</Button>
      </View>
    </View>)}
  </View>
}
