import type { DocumentContext, ProactiveNotification } from '../types';

export function proactiveDocumentReference(
  notification: ProactiveNotification,
): { fileId: string; filename: string } | null {
  if (notification.type !== 'opportunity_document_next_step') return null;
  const evidence = notification.evidence || {};
  const fileId = String(evidence.storage_key || evidence.file_id || '').trim();
  const filename = String(evidence.filename || '').trim();
  return fileId && filename ? { fileId, filename } : null;
}

export async function loadProactiveDocumentContext(
  notification: ProactiveNotification,
): Promise<DocumentContext | null> {
  const reference = proactiveDocumentReference(notification);
  if (!reference) return null;
  const { extractStoredPdfText } = await import('./reading');
  return { ...reference, text: await extractStoredPdfText(reference.fileId) };
}
