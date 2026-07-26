export const OPEN_RIGHT_WORKSPACE_EVENT = 'floris:open-right-workspace';

export function requestRightWorkspaceOpen(target: EventTarget): void {
  target.dispatchEvent(new Event(OPEN_RIGHT_WORKSPACE_EVENT));
}
