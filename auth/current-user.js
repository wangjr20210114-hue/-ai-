import { requireAuth } from '../cloud-functions/_jwt.js';

export async function currentUser(request, env) {
  if (String(env.AUTH_MODE || 'single_user') !== 'multi_user') return { id: 'local-user', username: 'local-user', roles: ['owner'] };
  const payload = await requireAuth({ request, env });
  return { id: String(payload.sub), username: String(payload.username || ''), roles: payload.roles || ['user'] };
}

export function tenantPrefix(user, env) {
  return String(env.AUTH_MODE || 'single_user') === 'multi_user' ? `tenants/${user.id}/` : '';
}
