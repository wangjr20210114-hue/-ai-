import assert from 'node:assert/strict';
import test from 'node:test';

import { conversationIndexUserId } from '../../auth/current-user.js';
import {
  belongsToUser,
  conversationItems,
  listUserConversations,
} from '../conversation-index.js';

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
