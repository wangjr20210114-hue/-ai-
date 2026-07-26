import { describe, expect, it, vi } from 'vitest';
import { OPEN_RIGHT_WORKSPACE_EVENT, requestRightWorkspaceOpen } from './workspaceEvents';

describe('workspace events', () => {
  it('requests a visible workspace when an action reveals its content', () => {
    const target = new EventTarget();
    const opened = vi.fn();
    target.addEventListener(OPEN_RIGHT_WORKSPACE_EVENT, opened);

    requestRightWorkspaceOpen(target);

    expect(opened).toHaveBeenCalledOnce();
  });
});
