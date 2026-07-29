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

const PRE_STYLE = [
  'margin:0 0 14px',
  'padding:20px 22px',
  'border-radius:18px',
  'background:#2b2233',
  'color:#f3edff',
  "font-family:Menlo,Consolas,monospace",
  'font-size:22px',
  'line-height:1.65',
  'white-space:pre-wrap',
  'word-break:break-all',
].join(';')

const RICH_TEXT_TAG_STYLES: Record<string, string> = {
  p: `margin:0 0 13px;line-height:1.75;${SERIF}`,
  h1: `margin:18px 0 10px;font-size:28px;font-weight:760;line-height:1.4;${SERIF}`,
  h2: `margin:16px 0 9px;font-size:26px;font-weight:720;line-height:1.4;${SERIF}`,
  h3: `margin:14px 0 7px;font-size:25px;font-weight:700;line-height:1.45;${SERIF}`,
  h4: `margin:12px 0 6px;font-size:24px;font-weight:680;line-height:1.5;${SERIF}`,
  h5: `margin:10px 0 5px;font-size:23px;font-weight:660;line-height:1.5;${SERIF}`,
  h6: `margin:10px 0 5px;font-size:22px;font-weight:640;line-height:1.5;${SERIF}`,
  ul: 'margin:0 0 13px;padding-left:36px',
  ol: 'margin:0 0 13px;padding-left:36px',
  li: `margin:6px 0;line-height:1.7;${SERIF}`,
  blockquote: `margin:0 0 13px;padding:6px 0 6px 20px;border-left:7px solid #ed6a2c;opacity:.82;${SERIF}`,
  a: 'color:#d9671f',
  strong: 'font-weight:700',
  code: `padding:2px 9px;border-radius:8px;background:rgba(237,106,44,.12);color:#d9671f;font-size:20px;${SERIF}`,
  hr: 'margin:20px 0;border-top:1px solid rgba(142,96,64,.16)',
  img: 'max-width:100%;border-radius:16px;margin:12px 0',
  table: `width:100%;margin:0 0 13px;border-collapse:collapse;font-size:22px;${SERIF}`,
  th: `padding:9px 12px;border:1px solid rgba(142,96,64,.24);background:rgba(237,106,44,.1);font-weight:660;text-align:left;line-height:1.55;${SERIF}`,
  td: `padding:9px 12px;border:1px solid rgba(142,96,64,.18);line-height:1.6;${SERIF}`,
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
