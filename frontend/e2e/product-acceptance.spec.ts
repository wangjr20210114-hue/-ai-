import { expect, test } from '@playwright/test';

import { installMockMakerApi } from './fixtures/mockMakerApi';


async function waitForApp(page: import('@playwright/test').Page) {
  await page.goto('/chatBot/');
  await expect(page.locator('.app-shell')).not.toHaveAttribute('aria-busy', 'true');
}

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
      { type: 'search_results', payload: { schema_version: 1, query: 'Maker-native architecture', results: [source], media: [], images: [], total: 1, media_pending: true, search_config: searchConfig } },
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
  expect(chatRequest?.headers['makers-conversation-id']).toBe('visual-baseline');
  expect(chatRequest?.body).not.toHaveProperty('tenant_id');
  expect(chatRequest?.body).not.toHaveProperty('user_id');
  expect(chatRequest?.body).not.toHaveProperty('membership');
});

test('trusted Skills expose their component actions through the marketplace boundary', async ({ page }) => {
  await installMockMakerApi(page);
  await waitForApp(page);

  await page.locator('[data-onboarding="skills"]').click();
  await expect(page.locator('.skills-page')).toBeVisible();
  await page.locator('.skills-page-nav > button').nth(3).click();
  await expect(page.locator('.component-api-list')).toContainText('proactive.refresh');
  await expect(page.locator('.component-api-list')).toContainText('proactive:read');
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
  const start = Date.parse('2026-08-01T10:00:00+08:00') / 1000;
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
