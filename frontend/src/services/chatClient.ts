import type { ChatQueueItem } from '../features/chat/model';

export type ChatSendResult = 'started' | 'queued' | 'queue_full' | 'ignored';

/** Client-facing turn controls shared by every Floris transport. */
export interface ChatClient {
  send(message: unknown): Promise<ChatSendResult> | ChatSendResult;
  stop?(): Promise<'confirmed' | 'local'>;
  queuedTurns?(): ChatQueueItem[];
  updateQueuedTurn?(clientMessageId: string, content: string): boolean;
  removeQueuedTurn?(clientMessageId: string): boolean;
  interruptWithQueuedTurn?(clientMessageId: string): Promise<'confirmed' | 'local' | 'started'>;
  close(): void;
}
