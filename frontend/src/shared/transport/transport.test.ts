import { afterEach, describe, expect, it, vi } from 'vitest';

import { HttpClientError, requestJson } from './httpClient';
import { splitSseFrames, streamEvents } from './sseClient';


afterEach(() => {
  vi.unstubAllGlobals();
});

describe('shared transport', () => {
  it('uses signed same-origin credentials for JSON requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    await expect(requestJson<{ ok: boolean }>('/auth/test')).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith(
      '/auth/test',
      expect.objectContaining({ credentials: 'same-origin' }),
    );
  });

  it('throws a typed error for non-2xx JSON responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: 'denied' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      }),
    ));
    const error = await requestJson('/auth/test').catch((value) => value);
    expect(error).toBeInstanceOf(HttpClientError);
    expect(error).toMatchObject({ status: 403, message: 'denied' });
  });

  it('decodes split UTF-8 SSE chunks without losing event boundaries', async () => {
    const bytes = new TextEncoder().encode(
      'data: {"type":"token","content":"你"}\n\n'
      + 'data: {"type":"done"}\n\n',
    );
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, bytes.length - 5));
        controller.enqueue(bytes.slice(bytes.length - 5));
        controller.close();
      },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })));
    const events: unknown[] = [];
    await streamEvents('/auth/stream', {}, { onEvent: (event) => events.push(event) });
    expect(events).toEqual([
      { type: 'token', content: '你' },
      { type: 'done' },
    ]);
  });

  it('retains incomplete SSE frames and honors abort', async () => {
    expect(splitSseFrames('data: {"type":"token"')).toEqual({
      frames: [],
      rest: 'data: {"type":"token"',
    });
    const controller = new AbortController();
    controller.abort();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(
      new DOMException('Aborted', 'AbortError'),
    ));
    await expect(
      streamEvents('/auth/stream', {}, { onEvent: () => undefined }, controller.signal),
    ).rejects.toMatchObject({ name: 'AbortError' });
  });
});
