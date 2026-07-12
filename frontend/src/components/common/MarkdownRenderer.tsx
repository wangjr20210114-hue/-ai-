import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import InfoCard from './InfoCard';
import type { RichMediaAsset, SearchMeta } from '../../types';
import { isSafeRemoteUrl, replaceCitationMarkers } from './richContent';

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
 * Resolve structured [[image:media-id]] markers. Legacy [[img:url]] remains
 * readable, but new answers never let the model provide the URL directly.
 */
function extractImages(
  content: string,
  media: RichMediaAsset[],
): { text: string; images: Map<number, RichMediaAsset> } {
  const images = new Map<number, RichMediaAsset>();
  let idx = 0;
  const text = content.replace(/\[\[(?:image|img):([^\]]+)\]\]/g, (marker, reference: string) => {
    const asset = resolveMediaReference(reference.trim(), media);
    if (!asset) return '';
    const id = idx;
    idx++;
    images.set(id, asset);
    return `ZIMG${id}Z`;
  });
  return { text, images };
}

function RichImage({ asset }: { asset: RichMediaAsset }) {
  const [failed, setFailed] = useState(false);
  // Hide broken images entirely instead of showing an error box
  if (failed) return null;
  return (
    <figure className="rich-media-figure">
      <img
        src={asset.url}
        alt={asset.alt || asset.caption || '回答配图'}
        loading="lazy"
        onError={() => setFailed(true)}
      />
      {(asset.caption || asset.source_url) && (
        <figcaption>
          <span>{asset.caption}</span>
          {asset.generated && <span className="rich-media-generated">AI 生成示意图</span>}
          {asset.source_url && isSafeRemoteUrl(asset.source_url) && (
            <a href={asset.source_url} target="_blank" rel="noreferrer">
              图片来源{asset.source_title ? `：${asset.source_title}` : ''}
            </a>
          )}
        </figcaption>
      )}
    </figure>
  );
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
    if (!isSafeRemoteUrl(url.trim())) return '';
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
    const props = children.props as { children?: React.ReactNode };
    return childrenToText(props.children);
  }
  return '';
}

/** 移除文本中的 ZIMG 标记 */
function stripImgMarkers(text: string): string {
  return text.replace(/ZIMG\d+Z/g, '').trim();
}

/** 从 React children 中移除 ZIMG 标记 */
function cleanImgMarkers(children: React.ReactNode): React.ReactNode {
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

export default function MarkdownRenderer({ content, searchMeta }: { content: string; searchMeta?: SearchMeta }) {
  const sources = searchMeta?.results || [];
  const media = searchMeta?.media || [];
  const cleanedContent = replaceCitationMarkers(content, sources);

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkMath, remarkGfm]}
        rehypePlugins={[rehypeKatex]}
        components={{
          h1: ({ children }) => <h1>{children}</h1>,
          h2: ({ children }) => <h2>{children}</h2>,
          h3: ({ children }) => <h3>{children}</h3>,
          p: ({ children }) => <p>{children}</p>,
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
          img: ({ src, alt }) => {
            const url = typeof src === 'string' ? src : '';
            if (!isSafeRemoteUrl(url)) return null;
            return (
              <RichImage asset={{
                id: `markdown-${url}`,
                kind: 'image',
                url,
                alt: alt || '',
                caption: alt || '',
                generated: false,
              }} />
            );
          },
          a: ({ href, children }) => {
            const url = typeof href === 'string' ? href : '';
            const text = typeof children === 'string' ? children : String(children || '');
            // Render known source links as cards
            const isCard = /zhihu\.com|weixin|baike\./i.test(url) || /知乎|公众号|百科/i.test(text);
            if (isCard && url) {
              return <InfoCard title={text} url={url} source="web" />;
            }
            return <a href={url} target="_blank" rel="noreferrer">{children}</a>;
          },
        }}
      >
        {cleanedContent}
      </ReactMarkdown>
    </div>
  );
}
