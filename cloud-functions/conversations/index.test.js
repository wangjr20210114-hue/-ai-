import assert from 'node:assert/strict';
import test from 'node:test';

import { conversationIndexUserId } from '../../auth/current-user.js';
import { authenticatedRequest, TEST_AUTH_ENV } from '../../test-utils/auth.js';
import {
  belongsToUser,
  conversationItems,
  conversationPointerKey,
  listUserConversations,
  touchConversationPointer,
  writeConversationPointer,
} from '../conversation-index.js';
import { onRequest } from './index.js';

const user = {
  id: 'floris:guest-1',
  tenant_id: 'floris',
};

function conversation(id, owner = user.id, tenant = user.tenant_id, lastMessageAt = 1) {
  return {
    conversationId: id,
    lastMessageAt,
    metadata: {
      client_conversation_id: id,
      owner_user_id: owner,
      tenant_id: tenant,
      title: id,
    },
  };
}

class FakeIndexStore {
  constructor() {
    this.values = new Map();
  }

  async setJSON(key, value) {
    this.values.set(key, value);
  }

  async list({ prefix }) {
    return {
      blobs: [...this.values.keys()]
        .filter((key) => key.startsWith(prefix))
        .map((key) => ({ key })),
    };
  }

  async get(key) {
    const value = this.values.get(key);
    if (value instanceof Error) throw value;
    return value || null;
  }
}

class FakeConversationRouteStore {
  async appendMessage(values) {
    this.appended = values;
    return 'native-message-1';
  }

  async getConversation({ conversationId }) {
    return {
      conversationId,
      createdAt: 100,
      lastMessageAt: 100,
      messageCount: 1,
      metadata: {},
    };
  }

  async updateConversation({ conversationId, metadata }) {
    return {
      conversationId,
      createdAt: 100,
      lastMessageAt: 101,
      messageCount: 1,
      metadata,
    };
  }
}

test('normalizes documented and legacy conversation list return shapes', () => {
  const item = conversation('yb7_shape');
  assert.deepEqual(conversationItems({ items: [item] }), [item]);
  assert.deepEqual(conversationItems({ conversations: [item] }), [item]);
  assert.deepEqual(conversationItems([item]), [item]);
  assert.deepEqual(conversationItems(null), []);
});

test('uses the documented descending user index when it has records', async () => {
  const calls = [];
  const expected = conversation('yb7_primary');
  const store = {
    async listConversations(args) {
      calls.push(args);
      return { items: [expected] };
    },
  };

  assert.deepEqual(await listUserConversations(store, user), [expected]);
  assert.deepEqual(calls, [{
    userId: await conversationIndexUserId(user.id),
    limit: 100,
    order: 'desc',
  }]);
});

test('uses a tenant-scoped Makers Blob pointer when native indexes are empty', async () => {
  const indexStore = new FakeIndexStore();
  const conversationId = 'yb7_11111111111111111111111111111111';
  const expected = await writeConversationPointer(indexStore, user, {
    conversationId,
    clientConversationId: 'yb7_client-pointer',
    title: 'Pointer title',
    now: 1_785_600_000_123,
  });
  const newer = await writeConversationPointer(indexStore, user, {
    conversationId: 'yb7_22222222222222222222222222222222',
    clientConversationId: 'yb7_client-newer',
    title: 'Newer pointer',
    now: 1_785_600_000_456,
  });
  indexStore.values.set(
    `tenants/floris/users/guest-1/conversation-index/v1/yb7_33333333333333333333333333333333.json`,
    new Error('corrupt pointer'),
  );
  const store = {
    async listConversations() {
      return { items: [] };
    },
  };

  assert.equal(
    conversationPointerKey(user, conversationId),
    `tenants/floris/users/guest-1/conversation-index/v1/${conversationId}.json`,
  );
  assert.deepEqual(
    await listUserConversations(store, user, { indexStore }),
    [newer, expected],
  );
});

test('touching a pointer preserves its title and creation time', async () => {
  const indexStore = new FakeIndexStore();
  const conversationId = 'yb7_44444444444444444444444444444444';
  const original = await writeConversationPointer(indexStore, user, {
    conversationId,
    clientConversationId: 'yb7_touch-client',
    title: 'Original title',
    messageCount: 1,
    now: 1_785_600_001_123,
  });
  const touched = await touchConversationPointer(indexStore, user, {
    conversationId,
    clientConversationId: 'yb7_touch-client',
    title: '',
    messageCount: 3,
    now: 1_785_600_001_456,
  });

  assert.equal(touched.metadata.title, 'Original title');
  assert.equal(touched.createdAt, original.createdAt);
  assert.equal(touched.messageCount, 3);
  assert.ok(touched.lastMessageAt > original.lastMessageAt);
});

test('conversation route writes its sidebar pointer through Makers Blob', async () => {
  const store = new FakeConversationRouteStore();
  const indexStore = new FakeIndexStore();
  const request = await authenticatedRequest('https://example.com/conversation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      operation: 'append_message',
      conversation_id: 'yb7_client-route',
      role: 'user',
      content: 'Pointer route title',
      metadata: { id: 'client-message-1' },
    }),
  });
  const response = await onRequest({
    request,
    env: TEST_AUTH_ENV,
    agent: { store },
    __indexStore: indexStore,
  });

  assert.equal(response.status, 200);
  assert.equal(indexStore.values.size, 1);
  const pointer = [...indexStore.values.values()][0];
  assert.equal(pointer.metadata.client_conversation_id, 'yb7_client-route');
  assert.equal(
    pointer.metadata.owner_user_id,
    'floris:11111111-1111-4111-8111-111111111111',
  );
  assert.match(store.appended.userId, /^uid_[0-9a-f]{40}$/);
});

test('touch_pointer writes through the unshadowed plural route', async () => {
  const indexStore = new FakeIndexStore();
  const request = await authenticatedRequest('https://example.com/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      operation: 'touch_pointer',
      conversation_id: 'yb7_plural-route',
      title: 'Plural route title',
      message_count: 2,
    }),
  });
  const response = await onRequest({
    request,
    env: TEST_AUTH_ENV,
    agent: { store: new FakeConversationRouteStore() },
    __indexStore: indexStore,
  });

  assert.equal(response.status, 200);
  assert.equal(indexStore.values.size, 1);
  const pointer = [...indexStore.values.values()][0];
  assert.equal(pointer.metadata.client_conversation_id, 'yb7_plural-route');
  assert.equal(pointer.metadata.title, 'Plural route title');
});

test('recovers through the paged global Makers index without leaking another tenant', async () => {
  const calls = [];
  const ownedFirst = conversation('yb7_owned-first', user.id, user.tenant_id, 20);
  const ownedSecond = conversation('yb7_owned-second', user.id, user.tenant_id, 10);
  const wrongUser = conversation('yb7_wrong-user', 'floris:guest-2', user.tenant_id, 30);
  const wrongTenant = conversation('yb7_wrong-tenant', user.id, 'other', 40);
  const store = {
    async listConversations(args) {
      calls.push(args);
      if (args.userId) return { items: [] };
      if (!args.after) {
        return {
          conversations: [wrongTenant, wrongUser, ownedFirst],
          next_cursor: 'global-page-2',
        };
      }
      return { items: [ownedSecond], nextCursor: '' };
    },
  };

  assert.deepEqual(await listUserConversations(store, user), [ownedFirst, ownedSecond]);
  assert.equal(calls.length, 6);
  assert.ok(calls.slice(0, 4).every((args) => args.userId));
  assert.deepEqual(calls[4], { limit: 100, order: 'desc' });
  assert.deepEqual(calls[5], { limit: 100, order: 'desc', after: 'global-page-2' });
  assert.equal(belongsToUser(wrongUser, user), false);
  assert.equal(belongsToUser(wrongTenant, user), false);
});

test('recovers when the optimized global descending scan is empty', async () => {
  const owned = conversation('yb7_global-ascending');
  const calls = [];
  const store = {
    async listConversations(args) {
      calls.push(args);
      if (args.userId || args.order === 'desc') return { items: [] };
      return { items: [owned] };
    },
  };

  assert.deepEqual(await listUserConversations(store, user), [owned]);
  assert.deepEqual(calls.at(-1), { limit: 100, order: 'asc' });
});
