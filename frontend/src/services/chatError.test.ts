import { afterEach, describe, expect, it, vi } from 'vitest';
import { presentableChatError } from './chatError';

describe('presentableChatError', () => {
  afterEach(() => vi.unstubAllGlobals());

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

  it('translates browser fetch failures into an actionable Chinese message', () => {
    expect(presentableChatError('Failed to fetch')).toBe('网络请求未能送达，请检查连接后重试。原问题不会自动重复发送。');
    expect(presentableChatError('Load failed')).not.toMatch(/failed/i);
  });

  it('localizes stable backend failure messages instead of leaking their source language', () => {
    vi.stubGlobal('localStorage', { getItem: () => 'en' });
    expect(presentableChatError('模型服务暂时未能处理本轮上下文，本次失败不会保存为 AI 回答；请点击重试。'))
      .toContain('could not process this request');
    expect(presentableChatError('模型服务当前繁忙或配额不足，请稍后重试。'))
      .toContain('busy or has reached its quota');
  });
});
