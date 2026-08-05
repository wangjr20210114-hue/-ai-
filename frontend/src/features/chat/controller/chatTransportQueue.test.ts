import { beforeEach, describe, expect, it, vi } from 'vitest';

const clientMocks = vi.hoisted(() => ({
  bootstrapApp: vi.fn(),
  openChatTurn: vi.fn(),
  requestConversationStop: vi.fn(),
  touchConversationIndex: vi.fn(),
}));

vi.mock('../model/client', () => clientMocks);
vi.mock('../../../services/browserLocation', () => ({
  browserLocationRequestContext: () => 'idle',
  currentBrowserLocation: () => null,
  requestBrowserLocationForChat: vi.fn(),
}));
vi.mock('../../../i18n', () => ({
  translate: (key: string) => key,
}));

import { SSEChatClient } from './chatTransport';

class MemoryStorage {
  private values = new Map<string, string>();

  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
  removeItem(key: string) { this.values.delete(key); }
  clear() { this.values.clear(); }
}

function turn(clientId: string) {
  return {
    type: 'chat',
    payload: {
      client_message_id: clientId,
      client_message: {
        id: clientId,
        role: 'user',
        content: clientId,
      },
    },
  };
}

function completedResponse() {
  return new Response('data: [DONE]\n\n', {
    status: 200,
    headers: { 'content-type': 'text/event-stream' },
  });
}

function pendingUntilAbort(signal: AbortSignal) {
  return new Promise<Response>((_resolve, reject) => {
    signal.addEventListener('abort', () => {
      const error = new Error('detached');
      error.name = 'AbortError';
      reject(error);
    }, { once: true });
  });
}

async function waitFor(check: () => boolean) {
  for (let index = 0; index < 80; index += 1) {
    if (check()) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  throw new Error('condition was not reached');
}

describe('chat transport FIFO durability', () => {
  beforeEach(() => {
    clientMocks.bootstrapApp.mockReset();
    clientMocks.openChatTurn.mockReset();
    clientMocks.requestConversationStop.mockReset();
    clientMocks.touchConversationIndex.mockReset().mockResolvedValue(undefined);
    const localStorage = new MemoryStorage();
    const sessionStorage = new MemoryStorage();
    vi.stubGlobal('window', {
      localStorage,
      sessionStorage,
      setTimeout,
      clearTimeout,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    });
    vi.stubGlobal('navigator', { onLine: true });
  });

  it('keeps the active FIFO head across a conversation switch and resumes only the successor', async () => {
    clientMocks.openChatTurn
      .mockImplementationOnce((_conversationId, _payload, signal) => (
        pendingUntilAbort(signal)
      ))
      .mockResolvedValueOnce(completedResponse());

    const firstClient = new SSEChatClient('conversation-switch');
    firstClient.connect(null);
    await firstClient.send(turn('client-active'));
    await waitFor(() => clientMocks.openChatTurn.mock.calls.length === 1);
    await firstClient.send(turn('client-successor'));
    firstClient.close();

    const restoredClient = new SSEChatClient('conversation-switch');
    restoredClient.connect({
      run_id: 'run-active',
      client_message_id: 'client-active',
      status: 'completed',
      error: '',
      diagnostics: {},
      started_at: 1,
      updated_at: 2,
      completed_at: 2,
    });
    await waitFor(() => clientMocks.openChatTurn.mock.calls.length === 2);
    expect(clientMocks.openChatTurn.mock.calls[1][1].client_message_id)
      .toBe('client-successor');
    restoredClient.close();
  });

  it('dequeues an explicitly stopped head only after confirmation and runs the queued successor', async () => {
    clientMocks.openChatTurn
      .mockImplementationOnce((_conversationId, _payload, signal) => (
        pendingUntilAbort(signal)
      ))
      .mockResolvedValueOnce(completedResponse());
    clientMocks.requestConversationStop.mockResolvedValue({ ok: true });

    const client = new SSEChatClient('conversation-stop');
    client.connect(null);
    await client.send(turn('client-stopped'));
    await waitFor(() => clientMocks.openChatTurn.mock.calls.length === 1);
    await client.send(turn('client-after-stop'));
    await client.stop();

    await waitFor(() => clientMocks.openChatTurn.mock.calls.length === 2);
    expect(clientMocks.requestConversationStop).toHaveBeenCalledWith(
      'conversation-stop',
      'client-stopped',
      expect.any(AbortSignal),
    );
    expect(clientMocks.openChatTurn.mock.calls[1][1].client_message_id)
      .toBe('client-after-stop');
    client.close();
  });

  it('confirms a timed-out stop from the same Maker run instead of reposting it', async () => {
    clientMocks.openChatTurn
      .mockImplementationOnce((_conversationId, _payload, signal) => (
        pendingUntilAbort(signal)
      ))
      .mockResolvedValueOnce(completedResponse());
    clientMocks.requestConversationStop.mockRejectedValue(
      Object.assign(new Error('deadline'), { name: 'AbortError' }),
    );
    clientMocks.bootstrapApp.mockResolvedValue({
      messages: [],
      run: {
        run_id: 'run-stopped',
        client_message_id: 'client-slow-stop',
        status: 'cancelled',
        error: '',
        diagnostics: {},
        started_at: 1,
        updated_at: 2,
        completed_at: 2,
      },
    });

    const client = new SSEChatClient('conversation-slow-stop');
    client.connect(null);
    await client.send(turn('client-slow-stop'));
    await waitFor(() => clientMocks.openChatTurn.mock.calls.length === 1);
    await client.send(turn('client-after-slow-stop'));
    expect(await client.stop()).toBe('confirmed');

    await waitFor(() => clientMocks.openChatTurn.mock.calls.length === 2);
    expect(clientMocks.bootstrapApp).toHaveBeenCalledWith(
      'conversation-slow-stop',
      expect.objectContaining({ strict: true }),
    );
    expect(clientMocks.requestConversationStop).toHaveBeenCalledTimes(1);
    expect(clientMocks.openChatTurn.mock.calls[1][1].client_message_id)
      .toBe('client-after-slow-stop');
    client.close();
  });
});
