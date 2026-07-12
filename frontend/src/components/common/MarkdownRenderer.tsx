import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import InfoCard from './InfoCard';
import type { RichMediaAsset, SearchMeta } from '../../types';
import { isSafeRemoteUrl, replaceCitationMarkers } from './richContent';

function RichImage({ asset }: { asset: RichMediaAsset }) {
  const [failed, setFailed] = useState(false);
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
              来源
            </a>
          )}
        </figcaption>
      )}
    </figure>
  );
}

const SOURCE_TYPE_MAP: Record<string, string> = {
  '公众号': 'wechat', '知乎': 'zhihu', '百科': 'baike', '网页': 'web',
  '论文': 'paper', '地点': 'location', '视频': 'video',
};

export default function MarkdownRenderer({ content, searchMeta }: { content: string; searchMeta?: SearchMeta }) {
  const sources = searchMeta?.results || [];
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
          li: ({ children }) => <li>{children}</li>,
          strong: ({ children }) => <strong>{children}</strong>,
          em: ({ children }) => <em>{children}</em>,
          blockquote: ({ children }) => <blockquote>{children}</blockquote>,
          hr: () => <hr />,
          table: ({ children }) => <table>{children}</table>,
          thead: ({ children }) => <thead>{children}</thead>,
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => <tr>{children}</tr>,
          th: ({ children }) => <th>{children}</th>,
          td: ({ children }) => <td>{children}</td>,
          a: ({ href, children }) => {
            const url = typeof href === 'string' ? href : '';
            const text = typeof children === 'string' ? children : String(children || '');
            const isCard = /zhihu\.com|weixin|baike\./i.test(url) || /知乎|公众号|百科/i.test(text);
            if (isCard && url) {
              const cardType = url.includes('zhihu') ? 'zhihu' : url.includes('weixin') ? 'wechat' : 'baike';
              return <InfoCard type={cardType} title={text} url={url} />;
            }
            return <a href={url} target="_blank" rel="noreferrer">{children}</a>;
          },
          img: ({ src, alt }) => {
            const url = typeof src === 'string' ? src : '';
            if (!isSafeRemoteUrl(url)) return null;
            return (
              <RichImage asset={{
                id: `md-${url.slice(-20)}`,
                kind: 'image', url,
                alt: alt || '', caption: alt || '',
                generated: false,
              }} />
            );
          },
        }}
      >
        {cleanedContent}
      </ReactMarkdown>
    </div>
  );
}
