import { requestJson } from '../../../shared/transport/httpClient';


export const routes = Object.freeze(['/skill_marketplace', '/skills', '/skill-uploads']);

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
