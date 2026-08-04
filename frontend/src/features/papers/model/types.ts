export interface PaperInfo {
  title: string;
  arxiv_id: string;
  authors: string;
  year: number;
  abstract_zh: string;
  key_contribution: string;
  citations: string;
  arxiv_url: string;
  pdf_url: string;
  source?: string;
  source_url?: string;
}

export interface StoredFileInfo {
  id: string;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  page_count: number;
  total_chars: number;
  preview: string;
  created_at: number;
  storage_key?: string;
  content_url?: string;
}

export type {
  PaperAssistantResult,
  ReadingFolder,
  ReadingSettings,
  SavedPaper,
} from './api';
