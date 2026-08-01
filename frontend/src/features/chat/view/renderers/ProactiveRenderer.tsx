import { Button } from 'tdesign-react';

import type { MessageBubbleController } from '../../controller/useMessageBubbleController';
import { useLanguage } from '../../../../i18n';
import type { ChatMessage, ProactiveState } from '../../../../shared/types';

interface Props {
  message: ChatMessage;
  proactive: ProactiveState | null;
  controller: MessageBubbleController;
}

export function ProactiveRenderer({ message, proactive, controller }: Props) {
  const { t } = useLanguage();
  if (!message.proactive || !proactive) return null;
  const { proactiveBusy, mutateProactive, applyProactiveSuggestion } = controller;
  return <div className="proactive-conversation-actions">
    {(proactive.notifications || [])
      .filter((item) => item.status !== 'dismissed')
      .slice(0, 3)
      .map((item) => <div className="proactive-conversation-item" key={item.id}>
        <span>{item.title}</span>
        <div>
          <Button size="small" variant="text" loading={proactiveBusy === `read:${item.id}`} onClick={() => { void applyProactiveSuggestion(item); }}>{t('handleForMe')}</Button>
          <Button size="small" variant="text" loading={proactiveBusy === `snooze:${item.id}`} onClick={() => void mutateProactive(`snooze:${item.id}`, 'snooze', { notification_id: item.id, until: Math.floor(Date.now() / 1000) + 3600 })}>{t('remindInHour')}</Button>
          <Button size="small" variant="text" loading={proactiveBusy === `dismiss:${item.id}`} onClick={() => void mutateProactive(`dismiss:${item.id}`, 'dismiss', { notification_id: item.id })}>{t('ignore')}</Button>
        </div>
      </div>)}
    {(proactive.workflows || [])
      .filter((item) => item.status === 'awaiting_confirmation')
      .map((workflow) => <div className="proactive-conversation-item" key={workflow.id}>
        <span>{t('ongoingTask', { title: workflow.title })}</span>
        <small>{workflow.reason}</small>
        <div>
          <Button size="small" theme="primary" loading={proactiveBusy === `workflow:${workflow.id}`} onClick={() => void mutateProactive(`workflow:${workflow.id}`, 'confirm_workflow', { workflow_id: workflow.id, version: workflow.version })}>{t('enableWorkflow')}</Button>
          <Button size="small" variant="text" onClick={() => void mutateProactive(`reject:${workflow.id}`, 'reject_workflow', { workflow_id: workflow.id, version: workflow.version })}>{t('notNow')}</Button>
        </div>
      </div>)}
    {(proactive.workflows || [])
      .filter((item) => item.status === 'active')
      .map((workflow) => {
        const step = workflow.steps.find(
          (item) => !['completed', 'skipped', 'compensated'].includes(item.status),
        );
        return <div className="proactive-conversation-item" key={workflow.id}>
          <span>{t('activeWorkflow', { title: workflow.title })}</span>
          <small>{step ? t('currentStep', { title: step.title }) : t('workflowSyncing')}</small>
          <div>
            {step && ['pending', 'notified'].includes(step.status) && <>
              <Button size="small" theme="success" loading={proactiveBusy === `complete:${step.id}`} onClick={() => void mutateProactive(`complete:${step.id}`, 'complete_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>{t('completeStep')}</Button>
              <Button size="small" variant="text" loading={proactiveBusy === `skip:${step.id}`} onClick={() => void mutateProactive(`skip:${step.id}`, 'skip_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>{t('skipStep')}</Button>
              <Button size="small" variant="text" loading={proactiveBusy === `fail:${step.id}`} onClick={() => void mutateProactive(`fail:${step.id}`, 'fail_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>{t('markFailed')}</Button>
            </>}
            {step?.status === 'compensating' && <Button size="small" theme="success" loading={proactiveBusy === `compensate:${step.id}`} onClick={() => void mutateProactive(`compensate:${step.id}`, 'compensate_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>{t('compensationComplete')}</Button>}
            {step && ['failed', 'attention_required'].includes(step.status) && <Button size="small" variant="outline" loading={proactiveBusy === `retry:${step.id}`} onClick={() => void mutateProactive(`retry:${step.id}`, 'retry_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>{t('retryStep')}</Button>}
            <Button size="small" variant="text" loading={proactiveBusy === `cancel:${workflow.id}`} onClick={() => void mutateProactive(`cancel:${workflow.id}`, 'cancel_workflow', { workflow_id: workflow.id, version: workflow.version })}>{t('stopWorkflow')}</Button>
          </div>
        </div>;
      })}
  </div>;
}
