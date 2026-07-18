import { describe, expect, it } from 'vitest';
import { presentableChatError } from './chatError';

describe('presentableChatError', () => {
  it('does not expose checkpoint role implementation errors', () => {
    expect(presentableChatError('role')).toContain('消息服务暂时异常');
    expect(presentableChatError("KeyError: 'role'")).not.toContain('KeyError');
  });

  it('hides invalid provider and model configuration details', () => {
    const raw = `Error code: 400 - {'error': {'message': 'Model ID must include provider prefix', 'type': 'invalid_request'}}`;
    expect(presentableChatError(raw)).toContain('模型配置');
    expect(presentableChatError(raw)).not.toContain('provider prefix');
  });

  it('keeps useful bounded user-facing messages', () => {
    expect(presentableChatError('今日 Token 预算已用完')).toBe('今日 Token 预算已用完');
    expect(presentableChatError('x'.repeat(220))).toHaveLength(181);
  });
});
