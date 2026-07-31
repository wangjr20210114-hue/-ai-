import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  ENTITLEMENT_CONTRACT,
  GUEST_SKILL_IDS,
  MEMBERSHIP_PLANS,
  PAYMENT_AVAILABLE,
  PLAN_LIMITS,
} from '../../auth/generated/entitlements.js';

const contract = JSON.parse(
  await readFile(new URL('../../contracts/entitlements.v1.json', import.meta.url), 'utf8'),
);

test('generated Node entitlement values preserve the canonical contract order', () => {
  assert.deepEqual(ENTITLEMENT_CONTRACT, contract);
  assert.deepEqual(MEMBERSHIP_PLANS, contract.plans);
  assert.deepEqual(GUEST_SKILL_IDS, contract.guest_skill_ids);
  assert.equal(PAYMENT_AVAILABLE, contract.payment_available);
  assert.deepEqual(Object.keys(PLAN_LIMITS), contract.plans);
});

test('generated Node entitlement values are recursively frozen', () => {
  assert.equal(Object.isFrozen(ENTITLEMENT_CONTRACT), true);
  assert.equal(Object.isFrozen(ENTITLEMENT_CONTRACT.limits.guest), true);
  assert.equal(Object.isFrozen(PLAN_LIMITS.pro), true);
});
