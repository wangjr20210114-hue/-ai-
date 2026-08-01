import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchPaperFile, streamPaper } from './paperApi';

afterEach(() => vi.unstubAllGlobals());

const TEST_AUTH_SESSION = {
  identity: {
    id: 'test:test-user',
    subject_id: 'test-user',
    tenant_id: 'test',
    username: 'tester',
    display_name: 'Tester',
    avatar_url: '',
    auth_type: 'wechat',
    membership: 'free',
    roles: ['user'],
  },
  entitlements: { plan: 'free', limits: {}, payment_available: false },
  login: {
    wechat_available: true,
    wechat_mode: 'qr',
    wechat_start_url: '/auth/wechat/start',
    logout_url: '/auth/logout',
  },
};

function authenticatedFetch(
  handler: (input: RequestInfo | URL, init?: RequestInit) => Response | Promise<Response>,
) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).startsWith('/auth/session')) {
      return Promise.resolve(new Response(JSON.stringify(TEST_AUTH_SESSION), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }));
    }
    return Promise.resolve(handler(input, init));
  });
}

function applicationCalls(fetchMock: ReturnType<typeof authenticatedFetch>) {
  return fetchMock.mock.calls.filter(([input]) => !String(input).startsWith('/auth/session'));
}

describe('fetchPaperFile', () => {
  it('uses one body request for a small Makers Blob object', async () => {
    const responses = [
      new Response(null, { headers: { 'content-length': '3', 'x-yuanbao-part-size': '4', 'content-type': 'application/pdf' } }),
      new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: { 'content-type': 'application/pdf' } }),
    ];
    const fetchMock = authenticatedFetch(() => responses.shift()!);
    vi.stubGlobal('fetch', fetchMock);

    const response = await fetchPaperFile('uploads/demo/small.pdf');
    expect(Array.from(new Uint8Array(await response.arrayBuffer()))).toEqual([1, 2, 3]);
    expect(applicationCalls(fetchMock)).toHaveLength(2);
  });

  it('joins authenticated parts for a file larger than a function response', async () => {
    const responses = [
      new Response(null, { headers: { 'content-length': '0', 'x-yuanbao-file-size': '7', 'x-yuanbao-part-size': '4', 'content-type': 'application/pdf' } }),
      new Response(new Uint8Array([1, 2, 3, 4]), { status: 200 }),
      new Response(new Uint8Array([5, 6, 7]), { status: 200 }),
    ];
    const fetchMock = authenticatedFetch(() => responses.shift()!);
    vi.stubGlobal('fetch', fetchMock);

    const response = await fetchPaperFile('uploads/demo/large.pdf');
    expect(Array.from(new Uint8Array(await response.arrayBuffer()))).toEqual([1, 2, 3, 4, 5, 6, 7]);
    const calls = applicationCalls(fetchMock);
    expect(calls).toHaveLength(3);
    expect(String(calls[1][0])).toContain('part=0');
    expect(String(calls[2][0])).toContain('part=1');
  });

  it('uses known size metadata to skip HEAD and starts every large-file part immediately', async () => {
    const pending: Array<() => void> = [];
    const fetchMock = authenticatedFetch((input: RequestInfo | URL) => new Promise<Response>((resolve) => {
      pending.push(() => {
        const part = Number(new URL(String(input), 'https://example.test').searchParams.get('part'));
        resolve(new Response(
          part === 0 ? new Uint8Array([1, 2, 3, 4]) : new Uint8Array([5, 6, 7]),
          { status: 200 },
        ));
      });
    }));
    vi.stubGlobal('fetch', fetchMock);

    const responsePromise = fetchPaperFile(
      'uploads/demo/known-large.pdf',
      undefined,
      { size: 7, partSize: 4 },
    );
    await vi.waitFor(() => expect(applicationCalls(fetchMock)).toHaveLength(2));
    pending.forEach((finish) => finish());

    const response = await responsePromise;
    expect(Array.from(new Uint8Array(await response.arrayBuffer()))).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(applicationCalls(fetchMock).every(([input]) => String(input).includes('part='))).toBe(true);
  });
});

describe('streamPaper', () => {
  it('emits incremental Markdown deltas from the Makers SSE reader', async () => {
    const encoder = new TextEncoder();
    const response = new Response(new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"type":"paper_delta","content":"## 结论"}\n\n'));
        controller.enqueue(encoder.encode('data: {"type":"paper_delta","content":"\\n\\n- 第一条"}\n\n'));
        controller.enqueue(encoder.encode('data: {"type":"paper_done"}\n\ndata: [DONE]\n\n'));
        controller.close();
      },
    }), {
      status: 200,
      headers: { 'content-type': 'text/event-stream; charset=utf-8' },
    });
    vi.stubGlobal('fetch', authenticatedFetch(() => response));
    const deltas: string[] = [];
    const result = await new Promise<{ full: string; error?: string }>((resolve) => {
      streamPaper(
        'translate',
        { text: 'source' },
        (delta) => deltas.push(delta),
        (full, error) => resolve({ full, error }),
      );
    });
    expect(deltas).toEqual(['## 结论', '\n\n- 第一条']);
    expect(result).toEqual({ full: '## 结论\n\n- 第一条', error: undefined });
  });
});
