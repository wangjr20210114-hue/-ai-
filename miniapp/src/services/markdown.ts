export function markdownToPlainText(markdown: string): string {
  return String(markdown || '')
    .replace(/!\[[^\]]*]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)]\((?:https?:\/\/|\/)[^)]*\)/g, '$1')
    .replace(/https?:\/\/\S+/g, '')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '• ')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/(\*\*|__|\*|_|~~|`{1,3})/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

/**
 * WeChat rich-text only honors inline styles reliably (page WXSS class
 * selectors cannot reach its inner nodes), so marked's HTML output gets
 * per-tag Floris typography injected here: headings, lists, quotes, code
 * blocks and tables all arrive styled.
 */

/* Serif stack matching the app: Times New Roman for latin, Songti for CJK. */
const SERIF = "font-family:'Times New Roman','Songti SC','STSong','SimSun','Noto Serif CJK SC',serif"

/* Runtime-injected styles bypass Taro's pxtransform, so every length here
   uses rpx directly (1rpx ≈ 0.5pt) — writing px would render ~2x too big. */
const PRE_STYLE = [
  'margin:0 0 20rpx',
  'padding:26rpx 30rpx',
  'border-radius:22rpx',
  'background:#2b2233',
  'color:#f3edff',
  "font-family:Menlo,Consolas,monospace",
  'font-size:22rpx',
  'line-height:1.65',
  'white-space:pre-wrap',
  'word-break:break-all',
].join(';')

const RICH_TEXT_TAG_STYLES: Record<string, string> = {
  p: `margin:0 0 20rpx;line-height:1.75;${SERIF}`,
  h1: `margin:28rpx 0 14rpx;font-size:27rpx;font-weight:760;line-height:1.4;${SERIF}`,
  h2: `margin:24rpx 0 12rpx;font-size:26rpx;font-weight:720;line-height:1.45;${SERIF}`,
  h3: `margin:20rpx 0 10rpx;font-size:25rpx;font-weight:700;line-height:1.5;${SERIF}`,
  h4: `margin:18rpx 0 9rpx;font-size:24rpx;font-weight:680;line-height:1.5;${SERIF}`,
  h5: `margin:16rpx 0 8rpx;font-size:23rpx;font-weight:660;line-height:1.5;${SERIF}`,
  h6: `margin:14rpx 0 7rpx;font-size:22rpx;font-weight:640;line-height:1.5;${SERIF}`,
  ul: 'margin:0 0 20rpx;padding-left:56rpx',
  ol: 'margin:0 0 20rpx;padding-left:56rpx',
  li: `margin:8rpx 0;line-height:1.7;${SERIF}`,
  blockquote: `margin:0 0 20rpx;padding:8rpx 0 8rpx 28rpx;border-left:8rpx solid #ed6a2c;opacity:.82;${SERIF}`,
  a: 'color:#d9671f',
  strong: 'font-weight:700',
  code: 'padding:4rpx 12rpx;border-radius:10rpx;background:rgba(237,106,44,.12);color:#d9671f;font-size:22rpx',
  hr: 'margin:32rpx 0;border-top:2rpx solid rgba(142,96,64,.16)',
  img: 'max-width:100%;border-radius:20rpx;margin:16rpx 0',
  table: `width:100%;margin:0 0 20rpx;border-collapse:collapse;font-size:22rpx;${SERIF}`,
  th: `padding:14rpx 18rpx;border:2rpx solid rgba(142,96,64,.24);background:rgba(237,106,44,.1);font-weight:660;text-align:left;line-height:1.55;${SERIF}`,
  td: `padding:14rpx 18rpx;border:2rpx solid rgba(142,96,64,.18);line-height:1.6;${SERIF}`,
}

export function decorateRichTextHtml(html: string): string {
  return String(html || '')
    // rich-text drops <pre> and a plain div collapses whitespace, so fenced
    // code becomes a dark card that preserves line breaks.
    .replace(/<pre(?:\s[^>]*)?><code(?:\s[^>]*)?>([\s\S]*?)<\/code><\/pre>/gi,
      (_match, inner: string) => `<div style="${PRE_STYLE}">${inner}</div>`)
    .replace(/<pre(?:\s[^>]*)?>([\s\S]*?)<\/pre>/gi,
      (_match, inner: string) => `<div style="${PRE_STYLE}">${inner}</div>`)
    // Only inject into tags without a style attribute (keeps the card above intact).
    .replace(/<([a-zA-Z][a-zA-Z0-9]*)((?:(?!style=)[^>])*)>/g,
      (match, tag: string, attrs: string) => {
        const style = RICH_TEXT_TAG_STYLES[tag.toLowerCase()]
        return style ? `<${tag}${attrs} style="${style}">` : match
      })
}
