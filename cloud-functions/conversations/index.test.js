import assert from 'node:assert/strict';
import test from 'node:test';

import { __test } from './index.js';

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

test('normalizes documented and legacy conversation list return shapes', () => {
  const item = conversation('yb7_shape');
  assert.deepEqual(__test.conversationItems({ items: [item] }), [item]);
  assert.deepEqual(__test.conversationItems({ conversations: [item] }), [item]);
  assert.deepEqual(__test.conversationItems([item]), [item]);
  assert.deepEqual(__test.conversationItems(null), []);
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

  assert.deepEqual(await __test.listUserConversations(store, user), [expected]);
  assert.deepEqual(calls, [{ userId: user.id, limit: 100, order: 'desc' }]);
});

test('recovers an empty optimized scan without leaking another tenant', async () => {
  const calls = [];
  const owned = conversation('yb7_owned', user.id, user.tenant_id, 20);
  const wrongUser = conversation('yb7_wrong-user', 'floris:guest-2', user.tenant_id, 30);
  const wrongTenant = conversation('yb7_wrong-tenant', user.id, 'other', 40);
  const store = {
    async listConversations(args) {
      calls.push(args);
      return args.order === 'desc'
        ? { items: [] }
        : { conversations: [wrongTenant, wrongUser, owned] };
    },
  };

  assert.deepEqual(await __test.listUserConversations(store, user), [owned]);
  assert.deepEqual(calls, [
    { userId: user.id, limit: 100, order: 'desc' },
    { userId: user.id, limit: 100, order: 'asc' },
  ]);
});
