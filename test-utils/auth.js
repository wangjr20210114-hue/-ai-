import { sessionCookie, signSessionToken } from '../auth/session.js';

export const TEST_AUTH_ENV = Object.freeze({
  JWT_SECRET: 'test-only-jwt-secret-with-more-than-32-characters',
  DEFAULT_TENANT_ID: 'floris',
});

export function testIdentity(overrides = {}) {
  return {
    sub: '11111111-1111-4111-8111-111111111111',
    tenant_id: 'floris',
    username: 'tester',
    display_name: '测试用户',
    avatar_url: '',
    auth_type: 'wechat',
    membership: 'free',
    roles: ['user'],
    session_version: 1,
    ...overrides,
  };
}

export async function authenticatedRequest(url, init = {}, identity = testIdentity(), env = TEST_AUTH_ENV) {
  const token = await signSessionToken(identity, env, 600);
  const headers = new Headers(init.headers || {});
  headers.set('Cookie', sessionCookie(token, { maxAge: 600, secure: false }).split(';', 1)[0]);
  return new Request(url, { ...init, headers });
}
