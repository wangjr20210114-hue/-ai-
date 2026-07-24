import { describe, expect, it } from 'vitest';
import type { ProactiveNotification } from '../types';
import { proactiveDocumentReference } from './proactiveDocument';

function notification(patch: Partial<ProactiveNotification> = {}): ProactiveNotification {
  return {
    id: 'n1', event_id: 'e1', run_id: 'r1', type: 'opportunity_document_next_step',
    title: '文档已就绪', body: '已保存', reason: 'upload', action_prompt: '总结文档',
    priority: 'normal', evidence: {}, status: 'unread', version: 1,
    created_at: 1, updated_at: 1, ...patch,
  };
}

describe('proactive document reference', () => {
  it('retains the Makers Blob key as non-visible typed context', () => {
    expect(proactiveDocumentReference(notification({
      evidence: { storage_key: 'uploads/conv/one.pdf', filename: '周报.pdf' },
    }))).toEqual({ fileId: 'uploads/conv/one.pdf', filename: '周报.pdf' });
  });

  it('loads the same document context for a proactive translation opportunity', () => {
    expect(proactiveDocumentReference(notification({
      type: 'opportunity_translation_review',
      evidence: { storage_key: 'uploads/conv/paper.pdf', filename: 'paper.pdf' },
    }))).toEqual({ fileId: 'uploads/conv/paper.pdf', filename: 'paper.pdf' });
  });

  it('ignores unrelated and incomplete notifications', () => {
    expect(proactiveDocumentReference(notification({ type: 'schedule_upcoming' }))).toBeNull();
    expect(proactiveDocumentReference(notification({ evidence: { filename: 'missing.pdf' } }))).toBeNull();
  });
});
