import { describe, expect, it } from 'vitest';
import { presentableChatError } from './chatError';

describe('presentableChatError', () => {
  it('does not expose checkpoint role implementation errors', () => {
    expect(presentableChatError('role')).toContain('消息服务暂时异常');
    expect(presentableChatError("KeyError: 'role'")).not.toContain('KeyError');
  });

  it('keeps useful bounded provider messages', () => {
    expect(presentableChatError('今日 Token 预算已用完')).toBe('今日 Token 预算已用完');
    expect(presentableChatError('x'.repeat(220))).toHaveLength(181);
  });
});
