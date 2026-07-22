export function hasTextSelectionInside(container: HTMLElement | null, selection: Selection | null): boolean {
  if (!container || !selection || selection.isCollapsed || !selection.anchorNode) return false;
  return container.contains(selection.anchorNode);
}
