import { expect, test } from '@playwright/test';

import { installMockMakerApi } from './fixtures/mockMakerApi';


async function waitForApp(page: import('@playwright/test').Page) {
  await page.goto('/chatBot/');
  await expect(page.locator('.app-shell')).not.toHaveAttribute('aria-busy', 'true');
}

test('guest keeps an explicit login entry while chat remains available', async ({ page }) => {
  await installMockMakerApi(page);
  await waitForApp(page);

  const login = page.getByRole('button', { name: '登录', exact: true });
  await expect(login).toBeVisible();
  await expect(login).toBeEnabled();
  await login.click();
  const dialog = page.locator('.auth-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('游客可直接聊天');
  await expect(dialog).toContainText('登录服务尚未配置');
  await expect(dialog).toHaveCSS('animation-name', 'auth-dialog-in');
  await page.getByRole('button', { name: '继续以游客身份使用', exact: true }).click();
  await expect(dialog).toBeHidden();

  await page.locator('.input-box textarea').fill('你好，请介绍一下你自己');
  await expect(page.locator('.input-submit-button')).toBeEnabled();
});

test('one planned search streams an answer and binds reviewed media to its exact source', async ({ page }) => {
  let chatRequest: { body: Record<string, unknown>; headers: Record<string, string> } | undefined;
  const source = {
    id: 'source-search',
    source: 'web',
    title: 'Maker-native architecture',
    snippet: 'The implementation reuses the signed Maker context.',
    url: 'https://example.test/maker-native',
    date: '2026-08-01',
  };
  const media = {
    id: 'media-search',
    kind: 'image',
    url: 'https://images.example.test/floris.jpg',
    source_id: source.id,
    source_url: source.url,
    source_title: source.title,
    alt: 'Maker-native boundary',
    caption: 'Reviewed and source-bound architecture evidence',
    generated: false,
    vision_reviewed: true,
  };
  const searchConfig = {
    turn_provider_calls: 1,
    turn_tool_invocations: 1,
  };
  await installMockMakerApi(page, {
    chatEvents: [
      { type: 'progress_event', payload: { schema_version: 1, stage: 'planning', status: 'completed', activity: 'general', source: 'controller' } },
      { type: 'search_results', payload: { schema_version: 1, query: 'Maker-native architecture', results: [source], media: [], images: [], total: 1, media_pending: true, timings_ms: { search: 2400 }, search_config: searchConfig } },
      { type: 'ai_response', content: `The result reuses the trusted Maker boundary. [View source](${source.url})` },
      { type: 'search_media', payload: { schema_version: 1, query: 'Maker-native architecture', results: [source], media: [media], images: [media.url], total: 1, media_pending: false, search_config: searchConfig } },
      { type: 'answer_complete', payload: { turn_id: 'turn-search-1' } },
    ],
    onChatRequest: (request) => { chatRequest = request; },
  });
  await waitForApp(page);

  await page.locator('.input-box textarea').fill('Find the latest Maker-native architecture evidence');
  await page.locator('.input-submit-button').click();

  const answer = page.locator('.msg-row.ai').last();
  await expect(answer).toContainText('trusted Maker boundary');
  const boundImage = answer.locator('img[data-source-id="source-search"]');
  await expect(boundImage).toHaveAttribute('data-source-bound-media', 'media-search');
  await expect(answer.locator('.markdown-body')).toHaveAttribute('data-search-provider-calls', '1');
  await expect(answer.locator('.markdown-body')).toHaveAttribute('data-search-tool-invocations', '1');
  // The public stopwatch covers the actual request-to-answer interval. The
  // mocked stream completes immediately, so it must not replace that duration
  // with SearchPro's provider-only 2.4 second diagnostic.
  await expect(answer.locator('.search-complete-meta')).toContainText('搜索 0.0 秒');
  expect(chatRequest?.headers['makers-conversation-id']).toBe('visual-baseline');
  expect(chatRequest?.body).not.toHaveProperty('tenant_id');
  expect(chatRequest?.body).not.toHaveProperty('user_id');
  expect(chatRequest?.body).not.toHaveProperty('membership');
});

test('trusted Skills expose component actions without leaking internal permission keys', async ({ page }) => {
  let marketplaceRequests = 0;
  await installMockMakerApi(page, {
    onSkillMarketplaceRequest: () => { marketplaceRequests += 1; },
  });
  await waitForApp(page);

  await page.locator('[data-onboarding="skills"]').click();
  await expect(page.locator('.skills-page')).toBeVisible();
  await page.getByRole('button', { name: '组件 API', exact: true }).click();
  await expect(page.locator('.skills-page-header')).toBeVisible();
  await expect(page.locator('.skills-page-brand')).toBeVisible();
  await expect(page.locator('.skills-page-account')).toBeVisible();
  await expect(page.locator('.component-api-list')).toContainText('calendar.change.propose');
  await expect(page.locator('.component-api-list')).not.toContainText('components.calendar');
  await expect(page.locator('.component-docs-toc-groups')).toContainText('日程');
  await expect(page.locator('.component-api-example')).toContainText('changes');
  const docs = page.locator('.component-docs');
  await expect.poll(() => page.locator('.skills-page-nav').evaluate(
    (element) => element.getBoundingClientRect().width,
  )).toBeLessThanOrEqual(210);
  await expect.poll(() => page.locator('.component-docs-toc').evaluate(
    (element) => element.getBoundingClientRect().width,
  )).toBeLessThanOrEqual(170);
  await expect(docs).toHaveClass(/is-toc-collapsed/);
  await page.locator('.component-docs-toc-toggle').click();
  await expect(docs).not.toHaveClass(/is-toc-collapsed/);
  await page.locator('.component-docs-toc-toggle').click();
  await expect(docs).toHaveClass(/is-toc-collapsed/);
  await page.evaluate(() => {
    document.documentElement.dataset.skillClosingObserved = '0';
    const marketplace = document.querySelector('.skills-page');
    if (!marketplace) throw new Error('Skills marketplace is not mounted');
    const observer = new MutationObserver(() => {
      if (marketplace.classList.contains('is-closing')) {
        document.documentElement.dataset.skillClosingObserved = '1';
        observer.disconnect();
      }
    });
    observer.observe(marketplace, { attributes: true, attributeFilter: ['class'] });
  });
  await page.locator('.skills-page-back').click();
  await expect.poll(() => page.evaluate(
    () => document.documentElement.dataset.skillClosingObserved,
  )).toBe('1');
  await expect(page.locator('.skills-page')).toBeHidden();
  await expect(page.locator('[data-onboarding="skills"] .t-loading')).toHaveCount(0);
  await page.clock.setFixedTime(new Date('2026-07-31T04:00:01.000Z'));
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('floris:auth-changed', {
    detail: {
      identity: {
        id: 'floris:user-1',
        subject_id: 'user-1',
        tenant_id: 'floris',
        username: 'user',
        display_name: '2011948918',
        avatar_url: '',
        auth_type: 'cloudbase',
        auth_providers: ['email'],
        membership: 'free',
        roles: ['user'],
      },
      entitlements: {
        plan: 'free', limits: { userSkillUploads: 2 }, payment_available: false,
      },
      login: {
        cloudbase_available: true,
        cloudbase_session_url: '',
        wechat_available: false,
        wechat_mode: 'qr',
        wechat_start_url: '',
        logout_url: '',
      },
    },
  })));
  await page.locator('[data-onboarding="skills"]').click();
  await expect.poll(() => marketplaceRequests).toBe(2);
  await expect(page.locator('.skills-page-account')).toContainText('已安全登录');
  await expect(page.locator('.skills-page-account')).toContainText('免费方案');
  await expect(page.locator('.skills-page-account')).not.toContainText('2011948918');
});

test('Skills remain installed while users can disable and re-enable them', async ({ page }) => {
  await installMockMakerApi(page);
  await waitForApp(page);

  await page.locator('[data-onboarding="skills"]').click();
  const proactive = page.locator('.skills-page-card').filter({
    has: page.getByRole('heading', { name: '主动服务', exact: true }),
  });
  await expect(proactive).toContainText('已启用');
  await proactive.getByRole('button', { name: '禁用', exact: true }).click();
  await expect(proactive).toContainText('已禁用');
  await expect(proactive.getByRole('button', { name: '启用', exact: true })).toBeVisible();
  await expect(proactive.getByRole('button', { name: '下载标准包', exact: true })).toBeVisible();

  await page.getByRole('button', { name: '已启用', exact: true }).click();
  await expect(proactive).toHaveCount(0);
  await page.getByRole('button', { name: '全部 Skills', exact: true }).click();
  await proactive.getByRole('button', { name: '启用', exact: true }).click();
  await expect(proactive).toContainText('已启用');
});

test('sending a question rejoins the live edge and scrolls to the bottom', async ({ page }) => {
  await installMockMakerApi(page, {
    messages: Array.from({ length: 18 }, (_, index) => ({
      id: `history-${index}`,
      role: index % 2 ? 'ai' : 'user',
      content: `历史消息 ${index} `.repeat(18),
      ts: index + 1,
    })),
    chatEvents: [
      { type: 'ai_response', content: '新问题的回答' },
      { type: 'answer_complete', payload: { turn_id: 'scroll-turn' } },
    ],
  });
  await waitForApp(page);
  await page.locator('.chat-scroll').evaluate((element) => { element.scrollTop = 0; });
  await page.locator('.input-box textarea').fill('把我带回当前问题');
  await page.locator('.input-submit-button').click();
  await expect.poll(() => page.locator('.chat-scroll').evaluate((element) => (
    element.scrollHeight - element.scrollTop - element.clientHeight
  ))).toBeLessThan(4);
});

test('a new conversation owns the next request without inheriting old rows', async ({ page }) => {
  let chatRequest: { body: Record<string, unknown>; headers: Record<string, string> } | undefined;
  await installMockMakerApi(page, {
    chatEvents: [
      { type: 'ai_response', content: 'Fresh conversation answer' },
      { type: 'answer_complete', payload: { turn_id: 'fresh-turn' } },
    ],
    onChatRequest: (request) => { chatRequest = request; },
  });
  await waitForApp(page);

  await expect(page.locator('.msg-row')).toHaveCount(2);
  const create = page.locator('[data-onboarding="new-conversation"]');
  await expect(create).toBeVisible();
  await create.click();
  await expect(page.locator('.msg-row')).toHaveCount(0);

  await page.locator('.input-box textarea').fill('Start a genuinely fresh turn');
  await page.locator('.input-submit-button').click();
  await expect(page.locator('.msg-row.ai')).toContainText('Fresh conversation answer');
  await expect(page.locator('.chat-scroll')).not.toContainText('鍙俊绯荤粺姝ｅ湪');
  expect(chatRequest?.headers['makers-conversation-id']).not.toBe('visual-baseline');
  expect(chatRequest?.headers['makers-conversation-id']).toMatch(/^yb7_/);
});

test('settings open through the feature controller without blocking on optional providers', async ({ page }) => {
  await installMockMakerApi(page);
  await waitForApp(page);

  await page.locator('[data-onboarding="settings"]').click();
  await expect(page.locator('.app-settings-dialog')).toBeVisible();
  await expect(page.locator('.settings-language-select')).toHaveValue('zh-CN');
  await expect(page.locator('.provider-usage-section')).toBeVisible();
});

test('two signed Maker sessions render isolated tenant state', async ({ browser }) => {
  const tenantA = await browser.newContext();
  const tenantB = await browser.newContext();
  const pageA = await tenantA.newPage();
  const pageB = await tenantB.newPage();
  await installMockMakerApi(pageA, {
    identity: { tenant_id: 'tenant-a', user_id: 'user-a', subject_id: 'tenant-a:user-a', display_name: 'Tenant A', auth_type: 'wechat', membership: 'plus' },
    messages: [{ id: 'a-only', role: 'ai', content: 'Tenant A private workspace', ts: 1 }],
  });
  await installMockMakerApi(pageB, {
    identity: { tenant_id: 'tenant-b', user_id: 'user-b', subject_id: 'tenant-b:user-b', display_name: 'Tenant B', auth_type: 'wechat', membership: 'plus' },
    messages: [{ id: 'b-only', role: 'ai', content: 'Tenant B private workspace', ts: 1 }],
  });

  await Promise.all([waitForApp(pageA), waitForApp(pageB)]);
  await expect(pageA.locator('.msg-row.ai')).toContainText('Tenant A private workspace');
  await expect(pageA.locator('body')).not.toContainText('Tenant B private workspace');
  await expect(pageB.locator('.msg-row.ai')).toContainText('Tenant B private workspace');
  await expect(pageB.locator('body')).not.toContainText('Tenant A private workspace');
  await expect(pageA.locator('header')).toContainText('Tenant A');
  await expect(pageB.locator('header')).toContainText('Tenant B');

  await tenantA.close();
  await tenantB.close();
});

test('calendar, map and paper features consume their owned Maker views', async ({ page }) => {
  const start = Date.parse('2026-07-31T10:00:00+08:00') / 1000;
  await installMockMakerApi(page, {
    messages: [{
      id: 'paper-result',
      role: 'ai',
      content: 'A verified paper result.',
      ts: start * 1000,
      papers: [{
        title: 'Deterministic Source Binding',
        authors: 'Floris Research',
        abstract_zh: 'A tenant-safe evidence architecture.',
        arxiv_id: '2608.00001',
        source: 'arXiv',
        source_url: 'https://arxiv.org/abs/2608.00001',
      }],
    }],
    messageState: {
      schedules: [{ id: 'schedule-1', title: 'Maker architecture review', start_time: start, duration_minutes: 60, location: 'Shenzhen' }],
      map_title: 'Maker architecture route',
      map_places: [{ id: 'place-1', name: 'Maker Studio', address: 'Shenzhen', latitude: 22.543, longitude: 114.0579, coordinate_type: 'gcj02' }],
    },
  });
  await waitForApp(page);

  await expect(page.locator('.makers-map-card')).toBeVisible();
  await expect(page.locator('.makers-map-title')).toContainText('Maker architecture route');
  await expect(page.locator('.calendar-day.has-events')).toHaveCount(1);
  await expect(page.locator('.paper-discovery-card')).toContainText('Deterministic Source Binding');
});
