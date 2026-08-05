import { beforeEach, describe, expect, it, vi } from 'vitest';

const transportMocks = vi.hoisted(() => ({
  authorizedFetch: vi.fn(),
}));

vi.mock('../../../shared/auth/session', () => ({
  authorizedFetch: transportMocks.authorizedFetch,
  withEdgeOneAuth: (value: string) => value,
}));

import { requestConversationStop } from './client';

describe('chat client Maker conversation boundary', () => {
  beforeEach(() => {
    transportMocks.authorizedFetch.mockReset().mockResolvedValue(
      new Response(JSON.stringify({ client_message_id: 'client-1' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });

  it('sends the same conversation id through Maker scope and stop payload', async () => {
    await requestConversationStop('conversation-1', 'client-1');

    expect(transportMocks.authorizedFetch).toHaveBeenCalledWith('/stop', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'makers-conversation-id': 'conversation-1',
      },
      body: JSON.stringify({
        conversation_id: 'conversation-1',
        client_message_id: 'client-1',
      }),
      signal: undefined,
    });
  });
});
