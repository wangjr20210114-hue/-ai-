import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  readManualStopClientMessageId,
  readManualStopIntent,
  TurnControlClient,
} from './turnControl';

describe('turn control', () => {
  const values = new Map<string, string>();
  beforeEach(() => {
    values.clear();
    vi.stubGlobal('window', {
      sessionStorage: {
        clear: () => values.clear(),
        getItem: (key: string) => values.get(key) ?? null,
        setItem: (key: string, value: string) => values.set(key, value),
        removeItem: (key: string) => values.delete(key),
      },
      clearTimeout,
      removeEventListener: () => undefined,
    });
  });

  it('persists one exact stop intent across a conversation switch or reload', () => {
    const control = new TurnControlClient('conversation-stop');
    control.markStopped('client-turn-1');
    expect(readManualStopIntent('conversation-stop')).toBe(true);
    expect(readManualStopClientMessageId('conversation-stop')).toBe('client-turn-1');
    control.clearStopIntent('client-turn-1');
    expect(readManualStopIntent('conversation-stop')).toBe(false);
    control.close();
  });

  it('does not let a late acknowledgement clear another turn stop intent', () => {
    const control = new TurnControlClient('conversation-race');
    control.markStopped('client-turn-2');
    expect(control.isStopped('client-turn-2')).toBe(true);
    expect(control.isStopped('client-turn-3')).toBe(false);
    control.clearStopIntent('client-turn-1');
    expect(readManualStopClientMessageId('conversation-race')).toBe('client-turn-2');
    control.close();
  });
});
