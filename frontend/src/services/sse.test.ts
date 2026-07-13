import { describe, expect, it } from 'vitest';
import { splitSseFrames } from './sse';

describe('splitSseFrames', () => {
  it('keeps partial frames and returns complete JSON events', () => {
    const parsed = splitSseFrames(
      'data: {"type":"ai_response","content":"你"}\n\ndata: {"type":"ai_',
    );
    expect(parsed.frames).toEqual(['{"type":"ai_response","content":"你"}']);
    expect(parsed.rest).toBe('data: {"type":"ai_');
  });

  it('supports CRLF and the DONE sentinel', () => {
    const parsed = splitSseFrames('data: {"type":"ping"}\r\n\r\ndata: [DONE]\r\n\r\n');
    expect(parsed.frames).toEqual(['{"type":"ping"}', '[DONE]']);
    expect(parsed.rest).toBe('');
  });
});
