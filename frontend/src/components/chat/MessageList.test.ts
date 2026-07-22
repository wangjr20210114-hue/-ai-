import { describe, expect, it } from 'vitest';
import { hasTextSelectionInside } from './scrollSelection';

describe('message selection auto-follow guard', () => {
  it('recognizes a non-collapsed selection inside the chat container', () => {
    const selectedNode = {} as Node;
    const container = { contains: (node: Node) => node === selectedNode } as HTMLElement;
    const selection = { isCollapsed: false, anchorNode: selectedNode } as unknown as Selection;
    expect(hasTextSelectionInside(container, selection)).toBe(true);
  });

  it('does not pause for a collapsed caret or an outside selection', () => {
    const selectedNode = {} as Node;
    const container = { contains: () => false } as unknown as HTMLElement;
    expect(hasTextSelectionInside(container, { isCollapsed: true, anchorNode: selectedNode } as unknown as Selection)).toBe(false);
    expect(hasTextSelectionInside(container, { isCollapsed: false, anchorNode: selectedNode } as unknown as Selection)).toBe(false);
  });
});
