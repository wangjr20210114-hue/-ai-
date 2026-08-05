import { beforeEach, describe, expect, it, vi } from 'vitest';

const transportMocks = vi.hoisted(() => ({
  authorizedFetch: vi.fn(),
}));

vi.mock('../../../shared/auth/session', () => ({
  authorizedFetch: transportMocks.authorizedFetch,
  withEdgeOneAuth: (value: string) => value,
}));

import { renameConversation, requestConversationStop } from './client';

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

  it('renames a conversation through the same tenant-scoped API', async () => {
    transportMocks.authorizedFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
        conversation: {
          conversationId: 'yb7_conversation-1',
          createdAt: 100,
          lastMessageAt: 200,
          messageCount: 2,
          metadata: { title: '杭州周末计划' },
        },
      }), { status: 200, headers: { 'content-type': 'application/json' } }),
    );

    const summary = await renameConversation('yb7_conversation-1', ' 杭州周末计划 ');
    expect(summary.title).toBe('杭州周末计划');
    expect(transportMocks.authorizedFetch).toHaveBeenCalledWith('/conversations', expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({
        'makers-conversation-id': 'yb7_conversation-1',
      }),
      body: JSON.stringify({
        operation: 'rename',
        conversation_id: 'yb7_conversation-1',
        title: '杭州周末计划',
      }),
    }));
  });
});
