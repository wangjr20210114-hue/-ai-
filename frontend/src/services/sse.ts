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
