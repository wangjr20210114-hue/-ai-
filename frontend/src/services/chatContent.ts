/** Remove only clearly UI-oriented follow-up sections leaked by the main model. */
export function stripInlineFollowUpSection(content: string): string {
  const marker = /(?:^|\n)\s{0,3}(?:#{1,6}\s*)?(?:后续(?:问题|追问)|延伸问题|接下来(?:可以|还可以)问|猜你想(?:继续)?问|你可能还想问|你还可以(?:继续)?问|可继续追问)\s*[:：]?\s*(?:\n|$)/i;
  const match = marker.exec(content);
  return match ? content.slice(0, match.index).trimEnd() : content;
}
