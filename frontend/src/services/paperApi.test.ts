import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchPaperFile } from './paperApi';

afterEach(() => vi.unstubAllGlobals());

describe('fetchPaperFile', () => {
  it('uses one body request for a small Makers Blob object', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { headers: { 'content-length': '3', 'x-yuanbao-part-size': '4', 'content-type': 'application/pdf' } }))
      .mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: { 'content-type': 'application/pdf' } }));
    vi.stubGlobal('fetch', fetchMock);

    const response = await fetchPaperFile('uploads/demo/small.pdf');
    expect(Array.from(new Uint8Array(await response.arrayBuffer()))).toEqual([1, 2, 3]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('joins authenticated parts for a file larger than a function response', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { headers: { 'content-length': '0', 'x-yuanbao-file-size': '7', 'x-yuanbao-part-size': '4', 'content-type': 'application/pdf' } }))
      .mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3, 4]), { status: 200 }))
      .mockResolvedValueOnce(new Response(new Uint8Array([5, 6, 7]), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const response = await fetchPaperFile('uploads/demo/large.pdf');
    expect(Array.from(new Uint8Array(await response.arrayBuffer()))).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[1][0])).toContain('part=0');
    expect(String(fetchMock.mock.calls[2][0])).toContain('part=1');
  });
});
