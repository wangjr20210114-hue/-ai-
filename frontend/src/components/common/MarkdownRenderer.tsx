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

function placeStableStreamingMedia(content: string, media: RichMediaAsset[] = []): string {
  const slotted = placeReviewedMedia(content, media, false);
  if (slotted !== content.replace(/\[\[YUANBAO_MEDIA[^\]]*$/, '')) return slotted;

  // When the model has not emitted a slot yet, show one useful image as soon
  // as the first prose block is complete.  That anchor never changes while
  // later tokens arrive, so selection and scroll position remain stable.
  const asset = media.find((candidate) => isSafeRemoteUrl(candidate.url));
  if (!asset) return slotted;
  const parts = content.split(/(\n{2,})/);
  for (let index = 0; index < parts.length - 1; index += 2) {
    const block = parts[index].trim();
    if (block && !/^(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|>|```|\|)/.test(block)) {
      parts[index] += mediaMarkdown(asset);
      return parts.join('');
    }
  }
  return slotted;
}

function followExternalLink(event: React.MouseEvent<HTMLAnchorElement>, url: string) {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  window.location.assign(url);
}

function RichImage({ asset }: { asset: RichMediaAsset }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  return (
    <figure className={`rich-media-figure${asset.preview ? ' is-preview' : ''}`}>
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
          {asset.preview && <span className="rich-media-reviewing">图片核实中</span>}
          {asset.generated && <span className="rich-media-generated">AI 生成示意图</span>}
          {asset.source_url && isSafeRemoteUrl(asset.source_url) && (
            <a href={asset.source_url} onClick={(event) => followExternalLink(event, asset.source_url!)}>
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

function uniqueMediaAssets(media: RichMediaAsset[]): RichMediaAsset[] {
  const seenUrls = new Set<string>();
  const seenCaptions = new Set<string>();
  return media.filter((asset) => {
    const url = asset.url.trim();
    const caption = (asset.caption || asset.alt || '').replace(/\s+/g, ' ').trim().toLocaleLowerCase();
    if (seenUrls.has(url) || (caption && seenCaptions.has(caption))) return false;
    seenUrls.add(url);
    if (caption) seenCaptions.add(caption);
    return true;
  });
}

function linkLabel(children: React.ReactNode): string {
  return React.Children.toArray(children)
    .filter((child): child is string | number => typeof child === 'string' || typeof child === 'number')
    .join('')
    .trim();
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
  const reviewedMedia = uniqueMediaAssets(searchMeta?.media || []);
  const visibleMedia = reviewedMedia.length
    ? reviewedMedia
    : uniqueMediaAssets(searchMeta?.media_pending ? searchMeta.preview_media || [] : []);
  // During streaming, an explicit model slot wins. If none has arrived, a
  // single image is anchored after the first completed prose block so it is
  // visible early without jumping as subsequent paragraphs grow.
  const cleanedContent = replaceCitationMarkers(
    streaming
      ? placeStableStreamingMedia(content, visibleMedia)
      : placeReviewedMedia(content, visibleMedia, true),
    sources,
  );
  const providerCalls = searchMeta?.search_config?.turn_provider_calls;
  const toolInvocations = searchMeta?.search_config?.turn_tool_invocations;

  return (
    <div
      className={`markdown-body${streaming ? ' is-streaming' : ''}`}
      data-search-provider-calls={typeof providerCalls === 'number' ? providerCalls : undefined}
      data-search-tool-invocations={typeof toolInvocations === 'number' ? toolInvocations : undefined}
    >
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
            if (!isSafeRemoteUrl(url)) return <>{children}</>;
            const label = linkLabel(children);
            const urlOnly = sameUrl(label.replace(/^<|>$/g, ''), url);
            const semanticCitation = /^(来源|出处|参考|source)$/i.test(label);
            const compactCitation = urlOnly || semanticCitation;
            return <a
              href={url}
              className={compactCitation ? 'md-citation-link' : undefined}
              title={compactCitation ? url : undefined}
              onClick={(event) => followExternalLink(event, url)}
            >{compactCitation ? '来源' : children}</a>;
          },
          img: ({ src, alt }) => {
            const url = typeof src === 'string' ? src : '';
            if (!isSafeRemoteUrl(url)) return null;
            const reviewed = visibleMedia.find((asset) => sameUrl(asset.url, url));
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
