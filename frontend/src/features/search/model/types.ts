export type {
  RichMediaAsset,
  SearchMeta,
  SearchResultItem,
} from '../../../shared/types';

export interface SearchEvent {
  type: 'stage' | 'sources' | 'media';
  payload: Record<string, unknown>;
  [key: string]: unknown;
}
