import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import hljs from 'highlight.js/lib/common';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import type { RichMediaAsset, SearchMeta } from '../../types';
import { isSafeRemoteUrl, replaceCitationMarkers } from './richContent';

const MEDIA_SLOT = /\[\[YUANBAO_MEDIA(?:\s*:\s*(\d+))?\]\]/g;

function markdownAlt(value: string): string {
  return value.replace(/[[\]\\]/g, '').replace(/\s+/g, ' ').trim().slice(0, 180) || '回答配图';
}

function mediaMarkdown(asset: RichMediaAsset): string {
  return `\n\n![${markdownAlt(asset.caption || asset.alt || '')}](${asset.url})\n\n`;
}

function placeMediaByAnswerStructure(content: string, media: RichMediaAsset[]): string {
  const safeMedia = media.filter((asset) => isSafeRemoteUrl(asset.url));
  if (!safeMedia.length) return content;

  // The answer model owns layout through explicit media slots. If it omitted
  // them while async vision review was still running, use the structure the
  // model did produce: distribute images after prose blocks, never as a fixed
  // gallery at the end.
  const parts = content.split(/(\n{2,})/);
  const prose = parts.reduce<number[]>((indices, part, index) => {
    if (
      index % 2 === 0
      && part.trim()
      && !/^(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|>|```|\|)/.test(part.trim())
    ) indices.push(index);
    return indices;
  }, []);
  const anchors = prose.length > 1 ? prose.slice(0, -1) : prose;
  if (anchors.length) {
    safeMedia.forEach((asset, index) => {
      const anchor = anchors[Math.min(
        anchors.length - 1,
        Math.floor((index * anchors.length) / safeMedia.length),
      )];
      parts[anchor] += mediaMarkdown(asset);
    });
    return parts.join('');
  }

  // A rare single-block answer still receives the image after its first
  // complete sentence, so the fallback is not hard-coded to the answer tail.
  const sentenceEnd = content.search(/[。！？.!?](?:\s|$)/);
  if (sentenceEnd >= 0) {
    const splitAt = sentenceEnd + 1;
    return `${content.slice(0, splitAt)}${safeMedia.map(mediaMarkdown).join('')}${content.slice(splitAt)}`;
  }
  return `${content}${safeMedia.map(mediaMarkdown).join('')}`;
}

function placeReviewedMedia(content: string, media: RichMediaAsset[] = [], allowStructuralFallback = true): string {
  let nextIndex = 0;
  let placedCount = 0;
  const placed = content.replace(MEDIA_SLOT, (_slot, explicitIndex: string | undefined) => {
    const requested = explicitIndex ? Math.max(0, Number(explicitIndex) - 1) : nextIndex++;
    const asset = media[requested];
    if (!asset || !isSafeRemoteUrl(asset.url)) return '';
    placedCount += 1;
    return mediaMarkdown(asset);
  });
  const cleaned = placed.replace(/\[\[YUANBAO_MEDIA[^\]]*$/, '');
  return placedCount > 0 || !allowStructuralFallback ? cleaned : placeMediaByAnswerStructure(cleaned, media);
}

function RichImage({ asset }: { asset: RichMediaAsset }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  return (
    <figure className="rich-media-figure">
      <img
        src={asset.url}
        alt={asset.alt || asset.caption || '回答配图'}
        loading="eager"
        decoding="async"
        draggable={false}
        onError={() => setFailed(true)}
      />
      {(asset.caption || asset.source_url) && (
        <figcaption>
          <span className="rich-media-caption-text">{asset.caption}</span>
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

export default function MarkdownRenderer({
  content,
  searchMeta,
  streaming = false,
}: {
  content: string;
  searchMeta?: SearchMeta;
  streaming?: boolean;
}) {
  const sources = searchMeta?.results || [];
  // While tokens are still arriving, only honor stable model-authored slots.
  // Recomputing fallback placement from an incomplete paragraph tree makes an
  // image jump between paragraphs and destroys the user's text selection.
  const cleanedContent = replaceCitationMarkers(
    placeReviewedMedia(content, searchMeta?.media || [], !streaming),
    sources,
  );

  return (
    <div className={`markdown-body${streaming ? ' is-streaming' : ''}`}>
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
            // Chat answers keep web evidence compact and readable. Dedicated
            // paper/location surfaces can still use InfoCard, but a Markdown
            // citation inside prose should remain a normal inline link.
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
