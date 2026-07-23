import React, { memo, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import hljs from 'highlight.js/lib/common';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import type { RichMediaAsset, SearchMeta } from '../../types';
import { isSafeRemoteUrl, linkBareCitations, replaceCitationMarkers, sourceLabel } from './richContent';

const MEDIA_SLOT = /\[\[YUANBAO_MEDIA(?:\s*:\s*(\d+))?\]\]/g;

function markdownAlt(value: string): string {
  return value.replace(/[[\]\\]/g, '').replace(/\s+/g, ' ').trim().slice(0, 180) || '回答配图';
}

function mediaMarkdown(asset: RichMediaAsset): string {
  return `\n\n![${markdownAlt(asset.caption || asset.alt || '')}](${asset.url})\n\n`;
}

function replaceLegacyMediaSlots(content: string, media: RichMediaAsset[] = []): string {
  let nextIndex = 0;
  const placed = content.replace(MEDIA_SLOT, (_slot, explicitIndex: string | undefined) => {
    const requested = explicitIndex ? Math.max(0, Number(explicitIndex) - 1) : nextIndex++;
    const asset = media[requested];
    if (!asset || !isSafeRemoteUrl(asset.url)) return '';
    return mediaMarkdown(asset);
  });
  return placed.replace(/\[\[YUANBAO_MEDIA[^\]]*$/, '');
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
            <a
              href={asset.source_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {asset.source_title || sourceLabel(asset.source_url)}
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

function MarkdownRenderer({
  content,
  searchMeta,
  streaming = false,
}: {
  content: string;
  searchMeta?: SearchMeta;
  streaming?: boolean;
}) {
  const sources = useMemo(() => searchMeta?.results || [], [searchMeta?.results]);
  const visibleMedia = useMemo(() => {
    const reviewedMedia = uniqueMediaAssets(searchMeta?.media || []);
    return reviewedMedia.length
      ? reviewedMedia
      : uniqueMediaAssets(searchMeta?.media_pending ? searchMeta.preview_media || [] : []);
  }, [searchMeta?.media, searchMeta?.media_pending, searchMeta?.preview_media]);
  // New answers contain ordinary model-authored Markdown images. Keep only a
  // narrow compatibility transform for historical messages that still carry
  // the former internal media marker; never guess a placement for new text.
  const cleanedContent = useMemo(() => {
    const mediaPlacedContent = replaceLegacyMediaSlots(content, visibleMedia);
    return replaceCitationMarkers(
      linkBareCitations(mediaPlacedContent, sources),
      sources,
    );
  }, [content, sources, visibleMedia]);
  const providerCalls = searchMeta?.search_config?.turn_provider_calls;
  const toolInvocations = searchMeta?.search_config?.turn_tool_invocations;
  const hasSearchMeta = Boolean(searchMeta);
  // Keep the renderer component identities stable. Completed answers still
  // re-render when header/proactive state changes; recreating these functions
  // would make React replace every Markdown node, interrupting native link
  // clicks and moving text selection between pointerdown and pointerup.
  const markdownComponents = useMemo(() => ({
    h1: ({ children }: { children?: React.ReactNode }) => <h1>{children}</h1>,
    h2: ({ children }: { children?: React.ReactNode }) => <h2>{children}</h2>,
    h3: ({ children }: { children?: React.ReactNode }) => <h3>{children}</h3>,
    p: ({ children }: { children?: React.ReactNode }) => <p>{children}</p>,
    ul: ({ children }: { children?: React.ReactNode }) => <ul>{children}</ul>,
    ol: ({ children }: { children?: React.ReactNode }) => <ol>{children}</ol>,
    li: ({ children }: { children?: React.ReactNode }) => <li>{children}</li>,
    strong: ({ children }: { children?: React.ReactNode }) => <strong>{children}</strong>,
    em: ({ children }: { children?: React.ReactNode }) => <em>{children}</em>,
    blockquote: ({ children }: { children?: React.ReactNode }) => <blockquote>{children}</blockquote>,
    hr: () => <hr />,
    table: ({ children }: { children?: React.ReactNode }) => <div className="md-table-wrap"><table>{children}</table></div>,
    thead: ({ children }: { children?: React.ReactNode }) => <thead>{children}</thead>,
    tbody: ({ children }: { children?: React.ReactNode }) => <tbody>{children}</tbody>,
    tr: ({ children }: { children?: React.ReactNode }) => <tr>{children}</tr>,
    th: ({ children }: { children?: React.ReactNode }) => <th>{children}</th>,
    td: ({ children }: { children?: React.ReactNode }) => <td>{children}</td>,
    pre: ({ children }: { children?: React.ReactNode }) => <CodeBlock>{children}</CodeBlock>,
    code: ({ className, children }: { className?: string; children?: React.ReactNode }) => (
      <code className={className || undefined}>{children}</code>
    ),
    a: ({ href, children }: { href?: string; children?: React.ReactNode }) => {
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
        target="_blank"
        rel="noopener noreferrer"
        className={compactCitation ? 'md-citation-link' : undefined}
        title={compactCitation ? url : undefined}
      >{compactCitation ? sourceLabel(url, sources) : children}</a>;
    },
    img: ({ src, alt }: { src?: string; alt?: string }) => {
      const url = typeof src === 'string' ? src : '';
      if (!isSafeRemoteUrl(url)) return null;
      const reviewed = visibleMedia.find((asset) => sameUrl(asset.url, url));
      // A searched answer may render only URLs that survived this turn's
      // visual review. This also removes a provisional URL when review
      // later rejects it. Non-search Markdown keeps normal image support.
      if (hasSearchMeta && !reviewed) return null;
      return <RichImage asset={reviewed || {
          id: `md-${url.slice(-20)}`,
          kind: 'image', url,
          alt: alt || '', caption: alt || '',
          generated: false,
        }} />;
    },
  }), [hasSearchMeta, sources, visibleMedia]);

  return (
    <div
      className={`markdown-body${streaming ? ' is-streaming' : ''}`}
      data-search-provider-calls={typeof providerCalls === 'number' ? providerCalls : undefined}
      data-search-tool-invocations={typeof toolInvocations === 'number' ? toolInvocations : undefined}
    >
      <ReactMarkdown
        remarkPlugins={[remarkMath, remarkGfm]}
        rehypePlugins={[rehypeKatex]}
        components={markdownComponents}
      >
        {cleanedContent}
      </ReactMarkdown>
    </div>
  );
}

// Header reminders, connection status, and other global state update more
// often than a completed answer. Do not rebuild an unchanged Markdown tree.
export default memo(MarkdownRenderer);
