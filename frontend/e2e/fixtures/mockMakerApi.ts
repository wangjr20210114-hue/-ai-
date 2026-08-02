import { resolve } from 'node:path';
import type { Page, Route } from '@playwright/test';

const now = Date.parse('2026-07-31T12:00:00+08:00');

const richMessages = [
  {
    id: 'user-baseline',
    role: 'user',
    content: '请总结今天的可信 AI 进展，并给出来源。',
    ts: now - 10_000,
  },
  {
    id: 'assistant-baseline',
    role: 'ai',
    content: [
      '## 今日摘要',
      '',
      '可信系统正在把**来源绑定**和最小权限运行时放到核心路径。',
      '',
      '详细证据见[架构说明](https://example.test/architecture)。',
    ].join('\n'),
    ts: now,
    followUps: ['解释可信 Adapter', '查看多租户边界'],
    searchResults: {
      schema_version: 1,
      query: '可信 AI 架构',
      results: [{
        id: 'source-architecture',
        source: 'web',
        title: '可信 AI 架构说明',
        snippet: '确定性来源绑定、最小权限与多租户隔离。',
        url: 'https://example.test/architecture',
        date: '2026-07-31',
      }],
      images: [],
      media: [{
        id: 'media-architecture',
        kind: 'image',
        url: 'https://images.example.test/floris.jpg',
        source_id: 'source-architecture',
        source_url: 'https://example.test/architecture',
        source_title: '可信 AI 架构说明',
        alt: 'Floris 可信架构示意',
        caption: '经视觉复核并与 source_id 精确绑定的媒体',
        generated: false,
        vision_reviewed: true,
      }],
      sources_used: ['web'],
      total: 1,
      media_pending: false,
      search_config: {
        result_limit: 6,
        image_limit: 2,
        parallel_image_search: true,
        media_delivery: 'progressive',
        provider_request_count: 1,
        page_fetch_limit: 3,
        turn_provider_calls: 1,
        turn_tool_invocations: 1,
      },
    },
  },
];

const marketplace = {
  skills: [
    {
      id: 'core',
      version: '1.0.0',
      kind: 'system',
      publisher: { id: 'floris', name: 'Floris', verified: true },
      required_plan: 'guest',
      category: 'foundation',
      order: 0,
      default_enabled: true,
      locked: true,
      capabilities: ['chat'],
      requires: [],
      recommends: ['proactive'],
      conflicts: [],
      external: false,
      configured: true,
      connect_url: '',
      icon: '◇',
      name: { 'zh-CN': '核心对话', en: 'Core chat' },
      description: { 'zh-CN': '可信系统组件与基础对话能力。', en: 'Trusted system component.' },
      component_actions: ['search.evidence.publish'],
      eligible: true,
      installed: true,
      enabled: true,
      eligibility_reason: '',
    },
    {
      id: 'proactive',
      version: '1.0.0',
      kind: 'system',
      publisher: { id: 'floris', name: 'Floris', verified: true },
      required_plan: 'guest',
      category: 'productivity',
      order: 1,
      default_enabled: true,
      locked: false,
      capabilities: ['proactive'],
      requires: ['core'],
      recommends: [],
      conflicts: [],
      external: false,
      configured: true,
      connect_url: '',
      icon: '✓',
      name: { 'zh-CN': '主动服务', en: 'Proactive service' },
      description: { 'zh-CN': '根据日程、路线与持续任务主动发现机会并提醒。', en: 'Proactive reminders for schedules, routes, and ongoing tasks.' },
      component_actions: [],
      eligible: true,
      installed: true,
      enabled: true,
      eligibility_reason: '',
    },
  ],
  preferences: { core: true, proactive: true },
  connections: {},
  entitlements: {
    plan: 'guest',
    limits: { search_results: 6 },
    payment_available: false,
  },
  dependency_graph: {
    nodes: [
      { id: 'core', version: '1.0.0', kind: 'system', locked: true, required_plan: 'guest', name: { 'zh-CN': '核心对话', en: 'Core chat' } },
      { id: 'proactive', version: '1.0.0', kind: 'system', locked: false, required_plan: 'guest', name: { 'zh-CN': '主动服务', en: 'Proactive service' } },
    ],
    edges: [{ from: 'proactive', to: 'core', type: 'requires' }],
  },
  component_api: {
    version: '1.0.0',
    actions: [{
      id: 'calendar.change.propose',
      category: 'calendar',
      name: { 'zh-CN': '展示日程变更', en: 'Show calendar changes' },
      permission: 'components.calendar',
      description: 'Render a calendar change proposal.',
      description_i18n: { 'zh-CN': '在日程组件中展示待确认的变更。', en: 'Render proposed changes in the calendar component.' },
      input: { changes: 'calendar-change[]', warnings: 'string[]' },
      required: ['changes'],
    }],
    security: {
      identity_source: 'signed_maker_context',
      model_is_authorization_boundary: false,
      tenant_prefix_required: true,
      raw_chain_of_thought_allowed: false,
    },
  },
  identity: {
    user_id: 'guest-visual',
    subject_id: 'guest-visual',
    tenant_id: 'tenant-visual',
    display_name: 'Guest',
    avatar_url: '',
    auth_type: 'guest',
    membership: 'guest',
    roles: [],
  },
};

function json(route: Route, body: unknown) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

export interface MockMakerApiOptions {
  identity?: Record<string, unknown>;
  messages?: Array<Record<string, unknown>>;
  messageState?: {
    schedules?: Array<Record<string, unknown>>;
    map_places?: Array<Record<string, unknown>>;
    map_title?: string;
  };
  workspace?: Record<string, unknown>;
  chatEvents?: Array<Record<string, unknown>>;
  onChatRequest?: (request: {
    body: Record<string, unknown>;
    headers: Record<string, string>;
  }) => void;
  onSkillMarketplaceRequest?: () => void;
}

export async function installMockMakerApi(
  page: Page,
  options: MockMakerApiOptions = {},
) {
  const identity = { ...marketplace.identity, ...(options.identity || {}) };
  let marketplacePreferences = { ...marketplace.preferences };
  let intelligenceSkillPreferences: Record<string, boolean> = {};
  await page.clock.setFixedTime(now);
  await page.addInitScript(() => {
    localStorage.setItem('floris-onboarding-preference', JSON.stringify({
      enabled: true,
      completedVersion: 1,
    }));
    localStorage.setItem('floris-language', 'zh-CN');
    localStorage.setItem('yuanbao.v6.conversationId', 'visual-baseline');
  });

  await page.route('**/auth/session', (route) => json(route, {
    identity,
    entitlements: {
      plan: 'guest',
      limits: {
        search_depth: 'standard',
        concurrent_runs: 1,
        daily_tokens: 10_000,
        user_skill_uploads: 0,
      },
      payment_available: false,
    },
    login: {
      wechat_available: false,
      wechat_mode: 'qr',
      wechat_start_url: '/auth/wechat/start',
      logout_url: '/auth/logout',
    },
  }));
  await page.route('https://images.example.test/floris.jpg', (route) => route.fulfill({
    status: 200,
    contentType: 'image/jpeg',
    path: resolve(process.cwd(), 'public/floris-chat-light.jpg'),
  }));
  await page.route('**/messages', (route) => json(route, {
    messages: options.messages || richMessages,
    schedules: options.messageState?.schedules || [],
    map_places: options.messageState?.map_places || [],
    map_title: options.messageState?.map_title || '',
    workspace_revision: 1,
    workspace_actions: [],
    run: null,
  }));
  await page.route('**/proactive', (route) => json(route, {
    schema_version: 1,
    revision: 1,
    preferences: {
      enabled: true,
      autonomy_mode: 'remind',
      timezone: 'Asia/Shanghai',
      quiet_hours: { enabled: false, start: '22:00', end: '07:00' },
      daily_limit: 8,
      lookahead_hours: 24,
      window_limit: 8,
      provider_schedule_limit: 8,
      route_gap_hours: 4,
      travel_buffer_minutes: 15,
      fallback_mottos: ['可信能力来自边界清晰的组件。'],
      types: {},
    },
    notifications: [],
    runs: [],
    workflows: [],
    checkpoints: {},
    last_tick: null,
  }));
  await page.route('**/conversations', (route) => json(route, {
    conversations: [{
      conversationId: 'visual-baseline',
      title: '视觉回归基线',
      createdAt: now - 60_000,
      lastMessageAt: now,
      messageCount: 2,
      metadata: {},
    }],
  }));
  await page.route('**/workspace', (route) => json(route, {
    revision: 1,
    schedules: [],
    map: null,
    actions: [],
    ...(options.workspace || {}),
  }));
  await page.route('**/intelligence', (route) => {
    const body = route.request().postDataJSON() as {
      operation?: string;
      preferences?: Record<string, boolean>;
    } | null;
    if (body?.operation === 'update_skill_preferences') {
      intelligenceSkillPreferences = {
        ...intelligenceSkillPreferences,
        ...(body.preferences || {}),
      };
      marketplacePreferences = {
        ...marketplacePreferences,
        ...(body.preferences || {}),
      };
    }
    return json(route, {
      search_preferences: {
        result_limit: 8,
        image_limit: 8,
        parallel_image_search: true,
      },
      map_preferences: {
        service_mode: 'balanced',
        place_result_limit: 6,
        route_stop_limit: 8,
        search_timeout_seconds: 30,
        preferred_route_mode: 'driving',
        route_strategy: 'time_then_cost',
        near_time_tolerance_minutes: 10,
        learn_route_preferences: true,
      },
      skill_preferences: intelligenceSkillPreferences,
      skill_catalog: [],
      skill_connections: {},
    });
  });
  await page.route('**/skill_marketplace', (route) => {
    options.onSkillMarketplaceRequest?.();
    return json(route, {
      ...marketplace,
      skills: marketplace.skills.map((skill) => ({
        ...skill,
        enabled: skill.locked || marketplacePreferences[skill.id] !== false,
      })),
      preferences: marketplacePreferences,
      identity,
    });
  });
  await page.route('**/library**', (route) => json(route, {
    items: [],
    folders: [],
    settings: { auto_organize: true },
  }));
  if (options.chatEvents) {
    await page.route('**/chat', async (route) => {
      const request = route.request();
      options.onChatRequest?.({
        body: request.postDataJSON() as Record<string, unknown>,
        headers: request.headers(),
      });
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream; charset=utf-8',
        body: [
          ...options.chatEvents!.map((event) => `data: ${JSON.stringify(event)}\n\n`),
          'data: [DONE]\n\n',
        ].join(''),
      });
    });
  }
  await page.route('**/provider_usage', (route) => json(route, {
    refreshed_at: now,
    usage: {
      daily_tokens: 0,
      monthly_tokens: 0,
      preferences: {
        daily_token_limit: 0,
        monthly_token_limit: 0,
        enforcement: 'off',
      },
      alerts: { daily: false, monthly: false },
    },
    metering: {
      daily: {},
      monthly: {},
      providers: {},
      recorded_events: 0,
      timezone: 'Asia/Shanghai',
    },
    providers: [],
  }));
}
