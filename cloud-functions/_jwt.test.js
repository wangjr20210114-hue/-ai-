import test from 'node:test';
import assert from 'node:assert/strict';
import { signToken, verifyToken } from './_jwt.js';

const env = { JWT_SECRET: '0123456789abcdef0123456789abcdef' };

test('official-style JWT round trip preserves tenant subject', async () => {
  const token = await signToken({ sub: 'user-a', username: 'alice', roles: ['user'] }, env, 60);
  const payload = await verifyToken(token, env);
  assert.equal(payload.sub, 'user-a');
  assert.equal(payload.username, 'alice');
});

test('JWT rejects tampering and expired tokens', async () => {
  const token = await signToken({ sub: 'user-a' }, env, 60);
  await assert.rejects(() => verifyToken(`${token.slice(0, -1)}x`, env));
  const expired = await signToken({ sub: 'user-a' }, env, -1);
  await assert.rejects(() => verifyToken(expired, env));
});
