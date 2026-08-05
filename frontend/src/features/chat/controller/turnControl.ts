import { bootstrapApp, requestConversationStop } from '../model/client';
import type { BootstrapData, MakersChatRun } from '../model';

const STOP_TIMEOUT_MS = 4_000;
const RECOVERY_POLL_MS = 2_000;
const MANUAL_STOP_PREFIX = 'floris:manual-stop:';

function stopStorageKey(conversationId: string): string {
  return `${MANUAL_STOP_PREFIX}${conversationId}`;
}

export function readManualStopClientMessageId(conversationId: string): string {
  try {
    const value = window.sessionStorage.getItem(stopStorageKey(conversationId)) || '';
    return value === '1' ? '' : value;
  } catch {
    return '';
  }
}

export function readManualStopIntent(conversationId: string): boolean {
  try {
    return Boolean(window.sessionStorage.getItem(stopStorageKey(conversationId)));
  } catch {
    return false;
  }
}

function writeManualStopIntent(
  conversationId: string,
  stopped: boolean,
  clientMessageId = '',
): void {
  try {
    if (stopped) {
      window.sessionStorage.setItem(
        stopStorageKey(conversationId),
        clientMessageId || '1',
      );
    } else {
      window.sessionStorage.removeItem(stopStorageKey(conversationId));
    }
  } catch {
    // Runtime state below remains authoritative for this tab.
  }
}

export function turnControlDelay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal?.aborted) {
      resolve();
      return;
    }
    const timer = window.setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      window.clearTimeout(timer);
      resolve();
    }, { once: true });
  });
}

export type TurnRecovery = {
  outcome: 'completed' | 'cancelled' | 'failed' | 'not_admitted';
  data?: BootstrapData;
  run?: MakersChatRun | null;
};

/** Cross-client turn lifecycle adapter over the Maker stop/messages APIs. */
export class TurnControlClient {
  private stopIntent: boolean;
  private stoppedClientId: string;
  private retryTimer: number | undefined;
  private onlineListener: (() => void) | undefined;
  private closed = false;

  constructor(private readonly conversationId: string) {
    this.stopIntent = readManualStopIntent(conversationId);
    this.stoppedClientId = readManualStopClientMessageId(conversationId);
  }

  get hasStopIntent(): boolean { return this.stopIntent; }
  get stopClientMessageId(): string { return this.stoppedClientId; }
  isStopped(clientMessageId: string): boolean {
    return Boolean(
      this.stopIntent
      && (
        !this.stoppedClientId
        || this.stoppedClientId === clientMessageId
      )
    );
  }

  markStopped(clientMessageId: string): void {
    this.stopIntent = true;
    this.stoppedClientId = clientMessageId;
    writeManualStopIntent(this.conversationId, true, clientMessageId);
  }

  clearStopIntent(clientMessageId = ''): void {
    if (clientMessageId && this.stoppedClientId && this.stoppedClientId !== clientMessageId) return;
    this.stopIntent = false;
    this.stoppedClientId = '';
    writeManualStopIntent(this.conversationId, false);
  }

  private clearRetry(): void {
    if (this.retryTimer) window.clearTimeout(this.retryTimer);
    this.retryTimer = undefined;
    if (this.onlineListener) {
      window.removeEventListener('online', this.onlineListener);
      this.onlineListener = undefined;
    }
  }

  private async attemptStop(clientMessageId: string): Promise<boolean> {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), STOP_TIMEOUT_MS);
    try {
      const response = await requestConversationStop(
        this.conversationId,
        clientMessageId,
        controller.signal,
      );
      return response.ok;
    } catch {
      return false;
    } finally {
      window.clearTimeout(timer);
    }
  }

  private scheduleStopRetry(clientMessageId: string, confirmed: () => void): void {
    this.clearRetry();
    const retry = () => {
      if (this.closed) return;
      void this.attemptStop(clientMessageId).then((ok) => {
        if (ok) {
          this.clearRetry();
          this.clearStopIntent(clientMessageId);
          confirmed();
          return;
        }
        this.scheduleStopRetry(clientMessageId, confirmed);
      });
    };
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      this.onlineListener = retry;
      window.addEventListener('online', retry, { once: true });
    } else {
      this.retryTimer = window.setTimeout(retry, RECOVERY_POLL_MS);
    }
  }

  async stop(clientMessageId: string, confirmed: () => void): Promise<'confirmed' | 'local'> {
    if (await this.attemptStop(clientMessageId)) {
      this.clearRetry();
      this.clearStopIntent(clientMessageId);
      confirmed();
      return 'confirmed';
    }
    this.scheduleStopRetry(clientMessageId, confirmed);
    return 'local';
  }

  async recover(
    expectedClientMessageId: string,
    signal: AbortSignal,
  ): Promise<TurnRecovery> {
    let absentChecks = 0;
    while (
      !this.closed
      && !signal.aborted
      && !this.isStopped(expectedClientMessageId)
    ) {
      if (typeof navigator !== 'undefined' && !navigator.onLine) {
        await turnControlDelay(RECOVERY_POLL_MS, signal);
        continue;
      }
      try {
        const data = await bootstrapApp(this.conversationId, {
          strict: true,
          timeoutMs: 8_000,
          signal,
        });
        const run = data.run;
        const sameTurn = Boolean(
          run
          && (!expectedClientMessageId || run.client_message_id === expectedClientMessageId),
        );
        if (sameTurn && (run?.status === 'running' || run?.status === 'cancel_requested')) {
          absentChecks = 0;
          await turnControlDelay(RECOVERY_POLL_MS, signal);
          continue;
        }
        if (sameTurn && run?.status === 'completed') return { outcome: 'completed', data, run };
        if (sameTurn && run?.status === 'cancelled') return { outcome: 'cancelled', data, run };
        if (sameTurn && run?.status === 'failed') return { outcome: 'failed', data, run };
        if (run?.status === 'running' || run?.status === 'cancel_requested') {
          await turnControlDelay(RECOVERY_POLL_MS, signal);
          continue;
        }
        absentChecks += 1;
        if (absentChecks >= 2) return { outcome: 'not_admitted', data, run };
      } catch {
        // A network recovery reads the existing Maker checkpoint only.
      }
      await turnControlDelay(RECOVERY_POLL_MS, signal);
    }
    return { outcome: 'cancelled' };
  }

  close(): void {
    this.closed = true;
    this.clearRetry();
  }
}
