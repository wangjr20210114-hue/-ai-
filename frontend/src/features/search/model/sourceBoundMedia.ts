import type { RichMediaAsset, SearchResultItem } from './types';

export interface MarkdownAstNode {
  type: string;
  value?: string;
  url?: string;
  alt?: string;
  children?: MarkdownAstNode[];
  data?: {
    hProperties?: Record<string, string>;
  };
}

interface SourceBoundMediaOptions {
  sources: SearchResultItem[];
  media: RichMediaAsset[];
  placeUncited?: boolean;
}

export function presentableSourceBoundMedia(item: RichMediaAsset): boolean {
  return item.vision_reviewed === true || (
    item.vision_reviewed === false
    && item.vision_fallback === true
    && item.source_bound_fallback === true
  );
}

type MarkdownTransformer = (tree: MarkdownAstNode) => void;
type MarkdownPlugin = () => MarkdownTransformer;

function safeRemoteUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return (url.protocol === 'https:' || url.protocol === 'http:')
      && !url.username
      && !url.password;
  } catch {
    return false;
  }
}

function linkedUrls(node: MarkdownAstNode): string[] {
  const urls: string[] = [];
  const visit = (current: MarkdownAstNode) => {
    if (current.type === 'link' && typeof current.url === 'string') {
      urls.push(current.url);
    }
    for (const child of current.children || []) visit(child);
  };
  visit(node);
  return urls;
}

export function stripLegacyMediaMarkers(content: string): string {
  return String(content || '')
    .replace(/\[\[YUANBAO_MEDIA(?:\s*:\s*\d+)?\]\]/gi, '')
    .replace(/\[\[YUANBAO_M[^\r\n]*/gi, '');
}

export function remarkSourceBoundMedia(
  options: SourceBoundMediaOptions,
): MarkdownPlugin {
  const sourceCounts = new Map<string, number>();
  for (const source of options.sources) {
    if (source.id) sourceCounts.set(source.id, (sourceCounts.get(source.id) || 0) + 1);
  }
  const sourceById = new Map<string, SearchResultItem>();
  for (const source of options.sources) {
    if (
      source.id
      && sourceCounts.get(source.id) === 1
      && safeRemoteUrl(source.url)
    ) {
      sourceById.set(source.id, source);
    }
  }
  const eligible = options.media.filter((item) => {
    const source = item.source_id ? sourceById.get(item.source_id) : undefined;
    return presentableSourceBoundMedia(item)
      && Boolean(item.id)
      && Boolean(source)
      && item.source_url === source?.url
      && safeRemoteUrl(item.url);
  });

  return () => (tree: MarkdownAstNode) => {
    const children = tree.children;
    if (!children?.length || !eligible.length) return;
    const placed = new Set<string>();
    for (let index = 0; index < children.length; index += 1) {
      const child = children[index];
      if (child.type !== 'paragraph') continue;
      const exactLinks = new Set(linkedUrls(child));
      const insertions = eligible
        .filter((item) => {
          const source = item.source_id ? sourceById.get(item.source_id) : undefined;
          return !placed.has(item.id)
            && Boolean(source)
            && exactLinks.has(String(source?.url));
        })
        .map((item): MarkdownAstNode => {
          placed.add(item.id);
          return {
            type: 'image',
            url: item.url,
            alt: item.alt || item.caption || '',
            data: {
              hProperties: {
                'data-source-bound-media': item.id,
                'data-source-id': String(item.source_id),
              },
            },
          };
        });
      if (!insertions.length) continue;
      children.splice(index + 1, 0, ...insertions);
      index += insertions.length;
    }
    if (!options.placeUncited) return;
    const remaining = eligible
      .filter((item) => !placed.has(item.id))
      .map((item): MarkdownAstNode => ({
        type: 'image',
        url: item.url,
        alt: item.alt || item.caption || '',
        data: {
          hProperties: {
            'data-source-bound-media': item.id,
            'data-source-id': String(item.source_id),
          },
        },
      }));
    if (!remaining.length) return;
    // Progressive media may finish for a source that the answer model did not
    // cite inline. Once the text stream is complete, keep those query-relevant
    // assets near the opening paragraph; RichImage still labels and links the
    // exact bound source. Never append a detached source directory at the end.
    let anchor = children.findIndex((child) => child.type === 'paragraph');
    if (anchor < 0) return;
    while (children[anchor + 1]?.type === 'image') anchor += 1;
    children.splice(anchor + 1, 0, ...remaining);
  };
}
