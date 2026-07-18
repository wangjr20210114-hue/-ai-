import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import hljs from 'highlight.js/lib/common';
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

function CodeBlock({ children }: { children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const child = React.Children.toArray(children)[0];
  if (!React.isValidElement<{ className?: string; children?: React.ReactNode }>(child)) {
    return <pre className="md-code-block">{children}</pre>;
  }
  const code = String(child.props.children || '').replace(/\n$/, '');
  const language = String(child.props.className || '').replace(/^language-/, '').trim();
  let highlighted = '';
  try {
    highlighted = language && hljs.getLanguage(language)
      ? hljs.highlight(code, { language, ignoreIllegals: true }).value
      : hljs.highlightAuto(code).value;
  } catch {
    highlighted = code.replace(/[&<>]/g, (value) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[value] || value));
  }
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch { setCopied(false); }
  };
  return <div className="md-code-shell">
    <div className="md-code-toolbar">
      <span>{language || '代码'}</span>
      <button type="button" onClick={() => { void copy(); }} aria-label="复制代码">{copied ? '已复制' : '复制'}</button>
    </div>
    <pre className="md-code-block"><code className={`hljs${language ? ` language-${language}` : ''}`} dangerouslySetInnerHTML={{ __html: highlighted }} /></pre>
  </div>;
}

function sameUrl(left: string, right: string): boolean {
  try {
    const normalize = (value: string) => {
      const url = new URL(value);
      url.hash = '';
      return url.toString().replace(/\/$/, '');
    };
    return normalize(left) === normalize(right);
  } catch { return left === right; }
}

function isVideoUrl(value: string): boolean {
  try {
    const host = new URL(value).hostname.toLowerCase();
    return /(^|\.)(bilibili\.com|youtube\.com|youtu\.be|v\.qq\.com|youku\.com|douyin\.com|ixigua\.com)$/.test(host);
  } catch { return false; }
}

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
          table: ({ children }) => <div className="md-table-wrap"><table>{children}</table></div>,
          thead: ({ children }) => <thead>{children}</thead>,
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => <tr>{children}</tr>,
          th: ({ children }) => <th>{children}</th>,
          td: ({ children }) => <td>{children}</td>,
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          code: ({ className, children }) => (
            <code className={className || undefined}>{children}</code>
          ),
          a: ({ href, children }) => {
            const url = typeof href === 'string' ? href : '';
            const text = typeof children === 'string' ? children : String(children || '');
            const source = sources.find((item) => sameUrl(item.url, url));
            const isKnownCard = /zhihu\.com|weixin|baike\./i.test(url) || /知乎|公众号|百科/i.test(text);
            if ((source || isKnownCard) && url && isSafeRemoteUrl(url)) {
              const cardType = source?.source === 'video' || isVideoUrl(url)
                ? 'video'
                : source?.source === 'zhihu' || url.includes('zhihu')
                  ? 'zhihu'
                  : source?.source === 'wechat' || url.includes('weixin')
                    ? 'wechat'
                    : source?.source === 'baike' || url.includes('baike')
                      ? 'baike'
                      : 'web';
              return <InfoCard
                type={cardType}
                title={text || source?.title || url}
                url={url}
                snippet={source?.snippet}
                image={source?.image}
                compact
              />;
            }
            return isSafeRemoteUrl(url) ? <a href={url} target="_blank" rel="noreferrer">{children}</a> : <>{children}</>;
          },
          img: ({ src, alt }) => {
            const url = typeof src === 'string' ? src : '';
            if (!isSafeRemoteUrl(url)) return null;
            const reviewed = searchMeta?.media?.find((asset) => sameUrl(asset.url, url));
            return <RichImage asset={reviewed || {
                id: `md-${url.slice(-20)}`,
                kind: 'image', url,
                alt: alt || '', caption: alt || '',
                generated: false,
              }} />;
          },
        }}
      >
        {cleanedContent}
      </ReactMarkdown>
    </div>
  );
}
