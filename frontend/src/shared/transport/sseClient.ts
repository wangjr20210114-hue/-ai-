/** Parse complete SSE frames while retaining the final partial frame. */
export function splitSseFrames(buffer: string): { frames: string[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, '\n');
  const chunks = normalized.split('\n\n');
  const rest = chunks.pop() || '';
  const frames = chunks
    .map((chunk) => chunk
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n'))
    .filter(Boolean);
  return { frames, rest };
}

export interface StreamEventHandlers {
  onEvent(event: unknown): void;
  onOpen?(response: Response): void;
}

export async function streamEvents(
  path: string,
  init: RequestInit,
  handlers: StreamEventHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const { authorizedFetch } = await import('../auth/session');
  const response = await authorizedFetch(path, { ...init, signal });
  if (!response.ok) {
    const detail = await response.text().catch(() => '');
    throw new Error(detail || `Stream request failed (${response.status})`);
  }
  handlers.onOpen?.(response);
  if (!response.body) return;

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const split = splitSseFrames(buffer);
    buffer = split.rest;
    for (const frame of split.frames) {
      try {
        handlers.onEvent(JSON.parse(frame));
      } catch {
        handlers.onEvent(frame);
      }
    }
    if (done) break;
  }
  const finalFrame = buffer.trim();
  if (finalFrame) {
    const data = finalFrame
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n');
    if (data) {
      try {
        handlers.onEvent(JSON.parse(data));
      } catch {
        handlers.onEvent(data);
      }
    }
  }
}
