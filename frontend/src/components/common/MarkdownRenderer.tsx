import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import InfoCard from './InfoCard';

const SOURCE_TYPE_MAP: Record<string, string> = {
  '公众号': 'wechat', '知乎': 'zhihu', '百科': 'baike', '网页': 'web',
  '论文': 'paper', '地点': 'location', '视频': 'video', '音乐': 'music',
  '书籍': 'book', '电影': 'movie',
};

interface ParsedCard {
  sourceType: string;
  title: string;
  url: string;
  snippet: string;
}

function stripMd(text: string): string {
  return text
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/`([^`]*)`/g, '$1')
    .trim();
}

/**
 * 提取所有 [[img:url]] 并替换为占位符 ZIMG{N}Z
 */
function extractImages(content: string): { text: string; images: Map<number, string> } {
  const images = new Map<number, string>();
  let idx = 0;
  const text = content.replace(/\[\[img:(https?:\/\/[^\]]+)\]\]/g, (_, url) => {
    const id = idx;
    idx++;
    images.set(id, url.trim());
    return `ZIMG${id}Z`;
  });
  return { text, images };
}

/**
 * 提取所有 [[card:...]] 并替换为占位符。
 * 用 ZCARD{N}Z 格式。
 */
function extractCards(content: string): { text: string; cards: Map<number, ParsedCard> } {
  const cards = new Map<number, ParsedCard>();
  const cardRegex = /\[\[card:([^|]+)\|([^|]+)\|([^|]+)(?:\|([^\]]*))?\]\]/g;
  let idx = 0;
  const text = content.replace(cardRegex, (_, sourceType, title, url, snippet) => {
    const id = idx;
    idx++;
    cards.set(id, {
      sourceType: sourceType.trim(),
      title: stripMd(title.trim()),
      url: url.trim(),
      snippet: stripMd((snippet || '').trim()),
    });
    return `ZCARD${id}Z`;
  });
  return { text, cards };
}

function extractCardIds(text: string): number[] {
  const ids: number[] = [];
  const regex = /ZCARD(\d+)Z/g;
  let m;
  while ((m = regex.exec(text)) !== null) {
    ids.push(parseInt(m[1], 10));
  }
  return ids;
}

function stripCardMarkers(text: string): string {
  return text.replace(/ZCARD\d+Z/g, '').trim();
}

function renderCards(ids: number[], cards: Map<number, ParsedCard>): React.ReactNode {
  return ids.filter(id => cards.has(id)).map(id => {
    const card = cards.get(id)!;
    const cardType = SOURCE_TYPE_MAP[card.sourceType] || 'web';
    return (
      <InfoCard
        key={id}
        type={cardType}
        sourceLabel={card.sourceType}
        title={card.title}
        url={card.url}
        snippet={card.snippet}
      />
    );
  });
}

/** 从 React children 中提取所有文本 */
function childrenToText(children: React.ReactNode): string {
  if (typeof children === 'string') return children;
  if (Array.isArray(children)) return children.map(childrenToText).join('');
  if (React.isValidElement(children)) {
    const props = children.props as any;
    return childrenToText(props.children);
  }
  return '';
}

/** 移除文本中的 ZIMG 标记 */
function stripImgMarkers(text: string): string {
  return text.replace(/ZIMG\d+Z/g, '').trim();
}

/** 从 React children 中移除 ZIMG 标记 */
function cleanImgMarkers(children: React.ReactNode, imgIds: number[]): React.ReactNode {
  if (typeof children === 'string') {
    return stripImgMarkers(children);
  }
  if (Array.isArray(children)) {
    return children.map(child => {
      if (typeof child === 'string') {
        const cleaned = stripImgMarkers(child);
        return cleaned || null;
      }
      return child;
    }).filter(Boolean);
  }
  return children;
}

/** 从 React children 中移除 ZCARD 标记文本节点 */
function cleanChildren(children: React.ReactNode): React.ReactNode {
  if (typeof children === 'string') {
    return stripCardMarkers(children);
  }
  if (Array.isArray(children)) {
    return children.map(child => {
      if (typeof child === 'string') {
        const cleaned = stripCardMarkers(child);
        return cleaned || null;
      }
      return child;
    }).filter(Boolean);
  }
  return children;
}

export default function MarkdownRenderer({ content }: { content: string }) {
  const { text: t1, images } = extractImages(content);
  const { text: mdText, cards } = extractCards(t1);

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkMath, remarkGfm]}
        rehypePlugins={[rehypeKatex]}
        components={{
          h1: ({ children }) => <h1>{children}</h1>,
          h2: ({ children }) => <h2>{children}</h2>,
          h3: ({ children }) => <h3>{children}</h3>,
          p: ({ children }) => {
            const rawText = childrenToText(children);
            // 处理图片占位符
            const imgIds: number[] = [];
            const imgRegex = /ZIMG(\d+)Z/g;
            let imgMatch;
            while ((imgMatch = imgRegex.exec(rawText)) !== null) {
              imgIds.push(parseInt(imgMatch[1], 10));
            }
            // 处理卡片占位符
            const cardIds = extractCardIds(rawText);

            if (cardIds.length > 0 || imgIds.length > 0) {
              const cardEls = renderCards(cardIds, cards);
              const imgEls = imgIds.filter(id => images.has(id)).map(id => (
                <img
                  key={`img-${id}`}
                  src={images.get(id)}
                  alt=""
                  loading="lazy"
                  style={{ width: '100%', borderRadius: 8, margin: '8px 0', display: 'block' }}
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
              ));
              // 清理占位符后的文字
              const cleanedChildren = cleanChildren(cleanImgMarkers(children, imgIds));
              const hasText = stripCardMarkers(stripImgMarkers(rawText)).trim().length > 0;
              if (!hasText) {
                return <>{imgEls}{cardEls}</>;
              }
              return (
                <>
                  <p>{cleanedChildren}</p>
                  {imgEls}
                  {cardEls}
                </>
              );
            }
            return <p>{children}</p>;
          },
          ul: ({ children }) => <ul>{children}</ul>,
          ol: ({ children }) => <ol>{children}</ol>,
          li: ({ children }) => {
            const rawText = childrenToText(children);
            const cardIds = extractCardIds(rawText);
            if (cardIds.length > 0) {
              const cardEls = renderCards(cardIds, cards);
              const hasText = stripCardMarkers(rawText).trim().length > 0;
              if (!hasText) {
                return <li style={{ listStyle: 'none', marginLeft: -18, marginBottom: 4 }}>{cardEls}</li>;
              }
              const cleanedChildren = cleanChildren(children);
              return <li>{cleanedChildren}</li>;
            }
            return <li>{children}</li>;
          },
          strong: ({ children }) => <strong>{children}</strong>,
          em: ({ children }) => <em>{children}</em>,
          blockquote: ({ children }) => <blockquote>{children}</blockquote>,
          hr: () => <hr />,
          a: ({ href, children }) => {
            // 检测来源角标：链接文字是"百科""公众号""知乎""网页"等来源类型词
            const text = typeof children === 'string' ? children.trim() : '';
            const SOURCE_WORDS = ['百科', '公众号', '知乎', '网页', '论文', '视频'];
            if (SOURCE_WORDS.includes(text)) {
              const colors: Record<string, string> = {
                '百科': '#e37318', '公众号': '#07c160', '知乎': '#0066ff', '网页': '#5a6072',
                '论文': '#7c5cff', '视频': '#ff6b6b',
              };
              const color = colors[text] || '#5a6072';
              return (
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  title={href}
                  style={{
                    fontSize: '0.7em',
                    color: `${color}aa`,
                    background: `${color}11`,
                    padding: '1px 5px',
                    borderRadius: 4,
                    margin: '0 2px',
                    textDecoration: 'none',
                    verticalAlign: 'super',
                    fontWeight: 500,
                    lineHeight: 1,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = `${color}22`; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = `${color}11`; }}
                >
                  {text}
                </a>
              );
            }
            return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
          },
          code: ({ children }) => <code>{children}</code>,
          pre: ({ children }) => <pre>{children}</pre>,
          table: ({ children }) => (
            <div className="md-table-wrap"><table>{children}</table></div>
          ),
          thead: ({ children }) => <thead>{children}</thead>,
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => <tr>{children}</tr>,
          th: ({ children }) => <th>{children}</th>,
          td: ({ children }) => {
            if (typeof children === 'string' && /ZCARD\d+Z/.test(children)) {
              return <td>{stripCardMarkers(children)}</td>;
            }
            if (Array.isArray(children)) {
              const cleaned = children.map(c =>
                typeof c === 'string' ? stripCardMarkers(c) : c
              );
              return <td>{cleaned}</td>;
            }
            return <td>{children}</td>;
          },
          img: ({ src, alt }) => (
            <img
              src={src}
              alt={alt || ''}
              loading="lazy"
              style={{ width: '100%', borderRadius: 8, margin: '8px 0' }}
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
          ),
        }}
      >
        {mdText}
      </ReactMarkdown>
    </div>
  );
}
