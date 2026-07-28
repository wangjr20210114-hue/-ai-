import { Image, Text, View } from '@tarojs/components'
import type { ChatMessage, WorkspaceAction } from '@floris/contracts'
import MarkdownMessage from './MarkdownMessage'
import ClarificationCard from './ClarificationCard'
import WorkspaceActionCard from './WorkspaceActionCard'
import PaperResults from './PaperResults'

interface Props {
  message: ChatMessage
  statusText?: string
  actionBusy?: string
  onClarification: (message: ChatMessage, values: Record<string, string | string[]>) => void
  onAction: (action: WorkspaceAction, operation: 'activate_map' | 'confirm_action' | 'cancel_action') => void
  onFollowUp: (value: string) => void
  onRetry: (message: ChatMessage) => void
}

export default function MessageBubble({
  message,
  statusText,
  actionBusy,
  onClarification,
  onAction,
  onFollowUp,
  onRetry,
}: Props) {
  const ai = message.role === 'ai'
  return <View className={`message-row ${ai ? 'assistant-row' : 'user-row'}`}>
    {ai ? <Image className='assistant-avatar' src='https://floris.jlutx.com/floris-avatar.png' mode='aspectFill' /> : null}
    <View className={`message-bubble ${ai ? 'assistant-bubble' : 'user-bubble'} ${message.failed ? 'failed-bubble' : ''}`}>
      {message.content ? <MarkdownMessage content={message.content} /> : null}
      {message.streaming && !message.content ? <View className='typing-dots'><Text>●</Text><Text>●</Text><Text>●</Text></View> : null}
      {message.streaming && statusText ? <Text className='stream-status'>{statusText}</Text> : null}
      {message.clarification ? <ClarificationCard
        prompt={message.clarification}
        answered={message.clarificationAnswered}
        disabled={message.streaming}
        onSubmit={(values) => onClarification(message, values)}
      /> : null}
      {(message.workspaceActions || []).map((action) => <WorkspaceActionCard
        key={action.id}
        action={action}
        busy={actionBusy === action.id}
        onExecute={onAction}
      />)}
      {message.papers?.length ? <PaperResults papers={message.papers} /> : null}
      {(message.followUps || []).length ? <View className='follow-ups'>
        {(message.followUps || []).map((item) => <ButtonLike key={item} text={item} onClick={() => onFollowUp(item)} />)}
      </View> : null}
      {message.failed
        ? <View className='retry-button' role='button' onClick={() => onRetry(message)}>重试生成</View>
        : null}
    </View>
  </View>
}

function ButtonLike({ text, onClick }: { text: string; onClick: () => void }) {
  return <View className='follow-up-chip' role='button' onClick={onClick}>{text}</View>
}
