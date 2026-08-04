import { requestJson } from '../../../shared/transport/httpClient';
import { requestRaw } from '../../../shared/transport/httpClient';
import type {
  SkillMarketplaceState,
  SkillUploadRecord,
  UserSkillRecord,
} from './types';


export const routes = Object.freeze(['/skill_marketplace', '/skill-uploads']);

export function loadSkillMarketplace<T>(
  conversationId: string,
  operation = 'get',
): Promise<T> {
  return requestJson<T>('/skill_marketplace', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify({ operation }),
  });
}

export async function skillMarketplaceOperation(
  conversationId: string,
): Promise<SkillMarketplaceState> {
  const data = await loadSkillMarketplace<SkillMarketplaceState>(
    conversationId,
    'catalog',
  );
  if (!Array.isArray(data.skills) || !data.dependency_graph || !data.component_api) {
    throw new Error('Could not load Skill marketplace');
  }
  return data;
}

export async function downloadSkillPackage(
  conversationId: string,
  skillId: string,
): Promise<void> {
  const data = await requestJson<{ package?: { filename: string } }>(
    '/skill_marketplace',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'makers-conversation-id': conversationId,
      },
      body: JSON.stringify({ operation: 'package', skill_id: skillId }),
    },
  );
  if (!data.package) throw new Error('Skill package download failed');
  const blob = new Blob([JSON.stringify(data.package, null, 2)], {
    type: 'application/vnd.floris.skill+json',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = data.package.filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function listSkillUploads(): Promise<SkillUploadRecord[]> {
  const data = await requestJson<{ uploads?: SkillUploadRecord[] }>(
    '/skill-uploads',
  );
  if (!Array.isArray(data.uploads)) throw new Error('Skill uploads unavailable');
  return data.uploads;
}

export async function uploadPrivateSkillPackage(file: File): Promise<SkillUploadRecord> {
  const intent = await requestJson<{
    upload_id?: string;
    storage_key?: string;
    url?: string;
  }>('/skill-uploads', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      operation: 'create',
      name: file.name,
      content_type: file.type || 'application/zip',
      size: file.size,
    }),
  });
  if (!intent.upload_id || !intent.storage_key || !intent.url) {
    throw new Error('Could not create Skill upload');
  }
  const stored = await requestRaw(intent.url, {
    method: 'PUT',
    headers: { 'Content-Type': file.type || 'application/zip' },
    body: file,
  }, false);
  if (!stored.ok) throw new Error(`Skill upload failed: HTTP ${stored.status}`);
  const result = await requestJson<{ upload?: SkillUploadRecord }>(
    '/skill-uploads',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        operation: 'complete',
        upload_id: intent.upload_id,
        storage_key: intent.storage_key,
        name: file.name,
      }),
    },
  );
  if (!result.upload) throw new Error('Could not store private Skill package');
  return result.upload;
}

export async function requestMarketplaceReview(uploadId: string): Promise<SkillUploadRecord> {
  const result = await requestJson<{ upload?: SkillUploadRecord }>(
    '/skill-uploads',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ operation: 'publish', upload_id: uploadId }),
    },
  );
  if (!result.upload) throw new Error('Could not request marketplace review');
  return result.upload;
}

export async function requestUserSkillMarketplaceReview(
  skill: UserSkillRecord,
): Promise<SkillUploadRecord> {
  const result = await requestJson<{ upload?: SkillUploadRecord }>(
    '/skill-uploads',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        operation: 'publish_declarative',
        source_skill_id: skill.id,
        name: skill.name,
        description: skill.description,
        instructions: skill.instructions,
        installed_at: skill.installed_at,
      }),
    },
  );
  if (!result.upload) throw new Error('Could not request marketplace review');
  return result.upload;
}
