export const DEFAULT_CLOUDBASE_ENV_ID = 'floris-auth-d3gd1pvebd6321d35';
export const DEFAULT_CLOUDBASE_REGION = 'ap-shanghai';

function safeEnvironmentId(value) {
  const normalized = String(value || '').trim();
  return /^[a-z][a-z0-9-]{5,62}$/i.test(normalized) ? normalized : '';
}

export function cloudBaseConfig(env = {}) {
  const environmentId = safeEnvironmentId(
    env.CLOUDBASE_ENV_ID || DEFAULT_CLOUDBASE_ENV_ID,
  );
  const region = String(
    env.CLOUDBASE_REGION || DEFAULT_CLOUDBASE_REGION,
  ).trim();
  if (!environmentId || region !== DEFAULT_CLOUDBASE_REGION) {
    throw new Error('CloudBase authentication configuration is invalid');
  }
  return {
    environmentId,
    region,
    gatewayOrigin: `https://${environmentId}.api.tcloudbasegateway.com`,
  };
}
