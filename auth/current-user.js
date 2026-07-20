export async function currentUser() {
  return { id: 'local-user', username: 'local-user', roles: ['owner'] };
}

export function tenantPrefix() {
  return '';
}
