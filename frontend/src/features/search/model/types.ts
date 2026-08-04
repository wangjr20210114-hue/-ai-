/** Source-bound rich-search contracts shared by chat and native renderers. */
export interface SearchResultItem {
  id: string;
  source: string;
  title: string;
  snippet: string;
  url: string;
  account_name?: string;
  gh_id?: string;
  avatar?: string;
  image?: string;
  date?: string;
}

export interface RichMediaAsset {
  id: string;
  kind: 'image' | 'generated_image' | string;
  url: string;
  source_id?: string;
  source_url?: string;
  source_title?: string;
  alt: string;
  caption: string;
  attribution?: string;
  generated: boolean;
  preview?: boolean;
  vision_reviewed?: boolean;
  source_bound_fallback?: boolean;
  vision_fallback?: boolean;
}

export interface ComponentPublication {
  version: string;
  action: string;
  payload: Record<string, unknown>;
}

export interface ComponentPublicationBatch {
  version: string;
  publications: ComponentPublication[];
}

export interface SearchMeta {
  schema_version?: number;
  query: string;
  results: SearchResultItem[];
  images: string[];
  media: RichMediaAsset[];
  preview_media?: RichMediaAsset[];
  sources_used: string[];
  total: number;
  target_date?: string;
  strict_date?: boolean;
  media_pending?: boolean;
  vision_diagnostics?: Record<string, number>;
  timings_ms?: Record<string, number>;
  component_api?: ComponentPublicationBatch;
  search_config?: {
    result_limit: number;
    image_limit: number;
    parallel_image_search: boolean;
    media_delivery?: 'disabled' | 'progressive' | 'blocking';
    provider_request_count: number;
    page_fetch_limit: number;
    turn_provider_calls?: number;
    turn_tool_invocations?: number;
  };
}
