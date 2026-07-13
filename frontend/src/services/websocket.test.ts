import { describe, expect, it } from 'vitest';
import { buildWebSocketUrl } from './websocket';

describe('buildWebSocketUrl', () => {
  it('uses ws and encodes the local conversation id', () => {
    expect(buildWebSocketUrl('default conversation', {
      protocol: 'http:',
      host: '127.0.0.1:5173',
    } as Location)).toBe('ws://127.0.0.1:5173/ws/default%20conversation');
  });

  it('uses wss on an HTTPS page', () => {
    expect(buildWebSocketUrl('makers-safe-id', {
      protocol: 'https:',
      host: 'example.test',
    } as Location)).toBe('wss://example.test/ws/makers-safe-id');
  });
});
