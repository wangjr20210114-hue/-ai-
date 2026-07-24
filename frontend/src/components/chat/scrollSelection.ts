export function hasTextSelectionInside(container: HTMLElement | null, selection: Selection | null): boolean {
  if (!container || !selection || selection.isCollapsed || !selection.anchorNode) return false;
  return container.contains(selection.anchorNode);
}

export function autoFollowAfterScroll(
  wasFollowing: boolean,
  previousScrollTop: number,
  scrollTop: number,
  distanceFromBottom: number,
): boolean {
  // Any upward movement is an explicit request to inspect earlier content.
  // Do not snap back even when that movement started only a few pixels above
  // the bottom while new streaming tokens are changing scrollHeight.
  if (scrollTop < previousScrollTop - 1) return false;
  // Following resumes only when the user actually reaches the bottom.
  if (distanceFromBottom <= 8) return true;
  return wasFollowing;
}
