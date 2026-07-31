import React, { memo, useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { RichMediaAsset, SearchMeta } from '../../types';
import { isSafeRemoteUrl, linkBareCitations, replaceCitationMarkers, sourceLabel } from './richContent';
import { translate, useLanguage } from '../../i18n';

const MEDIA_SLOT = /\[\[YUANBAO_MEDIA(?:\s*:\s*(\d+))?\]\]/g;

// Code highlighting and math typesetting are heavy and many conversations
// never use them. Load them after first paint, then upgrade the rendering.
interface MarkdownEnhancements {
  hljs: typeof import('highlight.js/lib/common').default;
  remarkMath: typeof import('remark-math').default;
  rehypeKatex: typeof import('rehype-katex').default;
}

let enhancementsCache: MarkdownEnhancements | null = null;
let enhancementsPromise: Promise<MarkdownEnhancements> | null = null;

// Exported so tests can preload the async chunks before a sync render.
export function loadMarkdownEnhancements(): Promise<MarkdownEnhancements> {
  if (!enhancementsPromise) {
    enhancementsPromise = Promise.all([
      import('highlight.js/lib/common'),
      import('remark-math'),
      import('rehype-katex'),
      import('katex/dist/katex.min.css'),
    ]).then(([hljsModule, remarkMathModule, rehypeKatexModule]) => {
      enhancementsCache = {
        hljs: hljsModule.default,
        remarkMath: remarkMathModule.default,
        rehypeKatex: rehypeKatexModule.default,
      };
      return enhancementsCache;
    });
  }
  return enhancementsPromise;
}

function useMarkdownEnhancements(): MarkdownEnhancements | null {
  const [enhancements, setEnhancements] = useState<MarkdownEnhancements | null>(() => enhancementsCache);
  useEffect(() => {
    if (enhancements) return;
    let alive = true;
    void loadMarkdownEnhancements().then((loaded) => { if (alive) setEnhancements(loaded); });
    return () => { alive = false; };
  }, [enhancements]);
  return enhancements;
}

function markdownAlt(value: string): string {
  return value.replace(/[[\]\\]/g, '').replace(/\s+/g, ' ').trim().slice(0, 180) || translate('answerImage');
}

function mediaMarkdown(asset: RichMediaAsset): string {
  return `\n\n![${markdownAlt(asset.caption || asset.alt || '')}](${asset.url})\n\n`;
}

function normalizedRemoteUrl(value: string): string {
  try {
    const url = new URL(value);
    url.hash = '';
    return url.toString().replace(/\/$/, '');
  } catch {
    return value.trim().replace(/\/$/, '');
  }
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

function placeSourceBoundMedia(
  content: string,
  media: RichMediaAsset[] = [],
  sources: SearchMeta['results'] = [],
): string {
  let placed = content;
  const usedSources = new Set<string>();
  for (const asset of media) {
    if (
      !asset.source_id
      || usedSources.has(asset.source_id)
      || !isSafeRemoteUrl(asset.url)
      || placed.includes(`](${asset.url})`)
    ) {
      continue;
    }
    const source = sources.find((item) => item.id === asset.source_id);
    if (
      !source
      || !isSafeRemoteUrl(source.url)
      || (
        asset.source_url
        && normalizedRemoteUrl(asset.source_url) !== normalizedRemoteUrl(source.url)
      )
    ) {
      continue;
    }
    const sourceUrlIndex = placed.indexOf(source.url);
    if (
      sourceUrlIndex < 2
      || placed.slice(sourceUrlIndex - 2, sourceUrlIndex) !== ']('
    ) {
      continue;
    }
    const citationEnd = sourceUrlIndex + source.url.length;
    const paragraphEnd = placed.indexOf('\n\n', citationEnd);
    const insertAt = paragraphEnd < 0 ? placed.length : paragraphEnd;
    const insertion = `\n\n${mediaMarkdown(asset).trim()}`;
    placed = `${placed.slice(0, insertAt)}${insertion}${placed.slice(insertAt)}`;
    usedSources.add(asset.source_id);
  }
  return placed;
}

function RichImage({ asset }: { asset: RichMediaAsset }) {
  const [failed, setFailed] = useState(false);
  const { t } = useLanguage();
  if (failed) return null;
  return (
    <figure className={`rich-media-figure${asset.preview ? ' is-preview' : ''}`}>
      <img
        src={asset.url}
        alt={asset.alt || asset.caption || t('answerImage')}
        loading="eager"
        decoding="async"
        draggable={false}
        onError={() => setFailed(true)}
      />
      {(asset.caption || asset.source_url) && (
        <figcaption>
          <span className="rich-media-caption-text">{asset.caption}</span>
          {asset.preview && <span className="rich-media-reviewing">{t('imageReviewing')}</span>}
          {asset.generated && <span className="rich-media-generated">{t('aiGeneratedIllustration')}</span>}
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
  const { t } = useLanguage();
  const enhancements = useMarkdownEnhancements();
  const child = React.Children.toArray(children)[0];
  if (!React.isValidElement<{ className?: string; children?: React.ReactNode }>(child)) {
    return <pre className="md-code-block">{children}</pre>;
  }
  const code = String(child.props.children || '').replace(/\n$/, '');
  const language = String(child.props.className || '').replace(/^language-/, '').trim();
  // Render plain code until the highlighter chunk arrives, then upgrade in place.
  let highlighted = '';
  if (enhancements) {
    const { hljs } = enhancements;
    try {
      highlighted = language && hljs.getLanguage(language)
        ? hljs.highlight(code, { language, ignoreIllegals: true }).value
        : hljs.highlightAuto(code).value;
    } catch {
      highlighted = code.replace(/[&<>]/g, (value) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[value] || value));
    }
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
      <span>{language || t('code')}</span>
      <button type="button" onClick={() => { void copy(); }} aria-label={t('copyCode')}>{copied ? t('copied') : t('copy')}</button>
    </div>
    {highlighted
      ? <pre className="md-code-block"><code className={`hljs${language ? ` language-${language}` : ''}`} dangerouslySetInnerHTML={{ __html: highlighted }} /></pre>
      : <pre className="md-code-block"><code className={language ? `language-${language}` : undefined}>{code}</code></pre>}
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
  const { t } = useLanguage();
  const enhancements = useMarkdownEnhancements();
  const sources = useMemo(() => searchMeta?.results || [], [searchMeta?.results]);
  const visibleMedia = useMemo(
    () => uniqueMediaAssets(searchMeta?.media || [])
      .filter((asset) => asset.vision_reviewed !== false),
    [searchMeta?.media],
  );
  // Legacy slots are cleaned for old conversations, but new answers never ask
  // the model to emit an internal media protocol. A reviewed image is inserted
  // only after a paragraph containing the exact source URL named by its
  // source_id; unmatched media fails closed instead of guessing a position.
  const cleanedContent = useMemo(() => {
    const legacyPlacedContent = replaceLegacyMediaSlots(content, visibleMedia);
    const linkedContent = replaceCitationMarkers(
      linkBareCitations(legacyPlacedContent, sources),
      sources,
    );
    return placeSourceBoundMedia(linkedContent, visibleMedia, sources);
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
      // Keep citations inside prose as compact, readable inline links.
      if (!isSafeRemoteUrl(url)) return <>{children}</>;
      const label = linkLabel(children);
      const urlOnly = sameUrl(label.replace(/^<|>$/g, ''), url);
      const semanticCitation = /^(?:来源|查看来源|出处|参考|來源|查看來源|出處|參考|source|view source)(?:\s*[:：·-]?\s*.*)?$/i.test(label);
      const compactCitation = urlOnly || semanticCitation;
      const citationHost = (() => {
        try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return sourceLabel(url, sources); }
      })();
      return <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className={compactCitation ? 'md-citation-link' : undefined}
        title={compactCitation ? url : undefined}
      >{compactCitation ? `${t('viewSource')} · ${citationHost}` : children}</a>;
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
  }), [hasSearchMeta, sources, t, visibleMedia]);

  return (
    <div
      className={`markdown-body${streaming ? ' is-streaming' : ''}`}
      data-search-provider-calls={typeof providerCalls === 'number' ? providerCalls : undefined}
      data-search-tool-invocations={typeof toolInvocations === 'number' ? toolInvocations : undefined}
    >
      <ReactMarkdown
        remarkPlugins={enhancements ? [enhancements.remarkMath, remarkGfm] : [remarkGfm]}
        rehypePlugins={enhancements ? [enhancements.rehypeKatex] : []}
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
