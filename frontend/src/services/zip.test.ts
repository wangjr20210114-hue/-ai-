import { describe, expect, it } from 'vitest';
import { createZip } from './zip';

describe('createZip', () => {
  it('creates local, central and end records for every entry', async () => {
    const blob = createZip([
      { name: '一.png', data: new Uint8Array([1, 2, 3]) },
      { name: '二.png', data: new Uint8Array([4, 5]) },
    ]);
    const bytes = new Uint8Array(await blob.arrayBuffer());
    const view = new DataView(bytes.buffer);
    expect(view.getUint32(0, true)).toBe(0x04034b50);
    expect(view.getUint32(bytes.length - 22, true)).toBe(0x06054b50);
    expect(view.getUint16(bytes.length - 14, true)).toBe(2);
    expect(blob.type).toBe('application/zip');
  });
});
