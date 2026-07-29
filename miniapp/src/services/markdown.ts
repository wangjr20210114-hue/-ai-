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

/* Keep rich content on the same native UI stack as the surrounding mini
   program. A single typographic voice is calmer on narrow screens and avoids
   the jump between Songti headings and system controls. */
const UI_FONT = "font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','PingFang SC','Helvetica Neue',Arial,sans-serif"

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
  p: `margin:0 0 22rpx;font-size:28rpx;line-height:1.72;${UI_FONT}`,
  // Chat headings should read as structure inside one answer, not as page
  // banners. Their slightly smaller size offsets the optical enlargement
  // caused by bold Chinese glyphs; weight and whitespace carry the hierarchy.
  h1: `margin:26rpx 0 12rpx;font-size:27rpx;font-weight:620;line-height:1.52;${UI_FONT}`,
  h2: `margin:24rpx 0 10rpx;font-size:27rpx;font-weight:610;line-height:1.54;${UI_FONT}`,
  h3: `margin:20rpx 0 9rpx;font-size:27rpx;font-weight:600;line-height:1.56;${UI_FONT}`,
  h4: `margin:20rpx 0 9rpx;font-size:27rpx;font-weight:590;line-height:1.56;${UI_FONT}`,
  h5: `margin:18rpx 0 8rpx;font-size:27rpx;font-weight:580;line-height:1.56;${UI_FONT}`,
  h6: `margin:18rpx 0 8rpx;font-size:27rpx;font-weight:570;line-height:1.56;${UI_FONT}`,
  ul: 'margin:0 0 20rpx;padding-left:56rpx',
  ol: 'margin:0 0 20rpx;padding-left:56rpx',
  li: `margin:8rpx 0;font-size:28rpx;line-height:1.68;${UI_FONT}`,
  blockquote: `margin:0 0 22rpx;padding:8rpx 0 8rpx 24rpx;border-left-width:6rpx;border-left-style:solid;border-left-color:#ed6a2c;opacity:.78;${UI_FONT}`,
  a: 'color:#d9671f',
  strong: 'font-weight:700',
  code: 'padding:4rpx 12rpx;border-radius:10rpx;background:rgba(237,106,44,.12);color:#d9671f;font-size:22rpx',
  hr: 'margin:32rpx 0;border-top:2rpx solid rgba(142,96,64,.16)',
  img: 'max-width:100%;border-radius:20rpx;margin:16rpx 0',
  table: `width:100%;margin:4rpx 0 22rpx;border-collapse:collapse;table-layout:fixed;font-size:22rpx;${UI_FONT}`,
  th: `padding:13rpx 10rpx;border:2rpx solid rgba(142,96,64,.2);background:rgba(237,106,44,.08);font-weight:660;text-align:left;line-height:1.45;${UI_FONT}`,
  td: `padding:13rpx 10rpx;border:2rpx solid rgba(142,96,64,.14);line-height:1.5;word-break:break-word;${UI_FONT}`,
}

export function decorateRichTextHtml(html: string): string {
  return String(html || '')
    // WeChat's rich-text applies an oversized native heading appearance on
    // some devices even when an h1-h6 carries an inline rpx font size. Render
    // headings as ordinary blocks so Floris owns the visual scale completely.
    .replace(/<h([1-6])([^>]*)>/gi,
      (_match, level: string, attrs: string) => {
        const style = RICH_TEXT_TAG_STYLES[`h${level}`]
        const cleanAttrs = String(attrs || '').replace(/\sstyle=(?:"[^"]*"|'[^']*')/gi, '')
        return `<div${cleanAttrs} style="${style}">`
      })
    .replace(/<\/h[1-6]>/gi, '</div>')
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
