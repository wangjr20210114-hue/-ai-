import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const sdk = vi.hoisted(() => {
  const auth = {
    getSession: vi.fn(),
    signInWithOAuth: vi.fn(),
    signInWithOtp: vi.fn(),
    signOut: vi.fn(),
  };
  return {
    auth,
    init: vi.fn(() => ({ auth: () => auth })),
  };
});

vi.mock('@cloudbase/js-sdk', () => ({
  default: { init: sdk.init },
}));

describe('CloudBase auth Adapter', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    vi.stubEnv('VITE_CLOUDBASE_ENV_ID', 'floris-auth-test');
    vi.stubEnv('VITE_CLOUDBASE_REGION', 'ap-shanghai');
    vi.stubEnv('VITE_CLOUDBASE_PUBLISHABLE_KEY', 'publishable-test-key');
    sdk.auth.getSession.mockResolvedValue({ data: { session: null }, error: null });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it('uses the official OTP callback returned by CloudBase', async () => {
    const verifyOtp = vi.fn();
    sdk.auth.signInWithOtp.mockResolvedValue({
      data: { verifyOtp },
      error: null,
    });
    const client = await import('./cloudbaseClient');

    await client.sendEmailOtp('reader@example.com');

    expect(client.cloudBaseConfigured).toBe(true);
    expect(sdk.init).toHaveBeenCalledWith(expect.objectContaining({
      env: 'floris-auth-test',
      region: 'ap-shanghai',
      accessKey: 'publishable-test-key',
      auth: { detectSessionInUrl: true },
    }));
    expect(sdk.auth.signInWithOtp).toHaveBeenCalledWith({
      email: 'reader@example.com',
      options: { shouldCreateUser: true },
    });
  });

  it('does not create a Floris session when CloudBase has no login to restore', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    const client = await import('./cloudbaseClient');

    await expect(client.restoreCloudBaseSession()).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('detects a provider-owned session for one-click account resume', async () => {
    sdk.auth.getSession.mockResolvedValue({
      data: { session: { access_token: 'saved-access-token' } },
      error: null,
    });
    const client = await import('./cloudbaseClient');

    await expect(client.hasRestorableCloudBaseSession()).resolves.toBe(true);
  });

  it('surfaces provider errors without falling back to a homemade auth flow', async () => {
    sdk.auth.signInWithOtp.mockResolvedValue({
      data: null,
      error: { message: 'Email login is disabled' },
    });
    const client = await import('./cloudbaseClient');

    await expect(client.sendEmailOtp('reader@example.com'))
      .rejects.toThrow('Email login is disabled');
  });

  it('fails clearly when CloudBase does not return a GitHub authorization URL', async () => {
    vi.stubGlobal('window', {
      location: {
        origin: 'https://preview.example.com',
        hostname: 'preview.example.com',
        pathname: '/chatBot',
        search: '?eo_token=test&eo_time=1',
        assign: vi.fn(),
      },
    });
    sdk.auth.signInWithOAuth.mockResolvedValue({ data: {}, error: null });
    const client = await import('./cloudbaseClient');

    await expect(client.startGithubLogin())
      .rejects.toThrow('CloudBase did not return a GitHub authorization URL');
  });
});
