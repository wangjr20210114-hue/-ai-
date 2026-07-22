#!/usr/bin/env node

/**
 * One-shot provider liveness audit.
 *
 * Reads a JSON environment snapshot, unlinks it before making network calls,
 * and prints only sanitized status/latency metadata. Secret values and raw
 * provider bodies are never logged.
 */

import { readFile, unlink } from 'node:fs/promises';

const pathIndex = process.argv.indexOf('--env-json');
if (pathIndex < 0 || !process.argv[pathIndex + 1]) {
  throw new Error('Usage: node tools/probe-providers.mjs --env-json /private/tmp/provider-env.json');
}

const envPath = process.argv[pathIndex + 1];
let env;
try {
  env = JSON.parse(await readFile(envPath, 'utf8'));
} finally {
  await unlink(envPath).catch(() => {});
}

const configured = (key) => Boolean(String(env[key] || '').trim());
const timeout = (milliseconds) => AbortSignal.timeout(milliseconds);
const onlyIndex = process.argv.indexOf('--only');
const only = new Set(
  onlyIndex >= 0 && process.argv[onlyIndex + 1]
    ? process.argv[onlyIndex + 1].split(',').map((item) => item.trim()).filter(Boolean)
    : [],
);
const selected = (name) => only.size === 0 || only.has(name);

async function jsonBody(response) {
  const text = await response.text();
  const eventData = text.trim().startsWith('data:')
    ? text.split('\n').find((line) => line.startsWith('data:'))?.slice(5).trim()
    : text;
  try { return JSON.parse(eventData || ''); }
  catch { return null; }
}

async function probe(name, required, operation) {
  if (!selected(name)) return { name, skipped: true };
  const missing = required.filter((key) => !configured(key));
  if (missing.length) return { name, configured: false, live: false, missing };
  const started = performance.now();
  try {
    const result = await operation();
    return { name, configured: true, latency_ms: Math.round(performance.now() - started), ...result };
  } catch (error) {
    return {
      name, configured: true, live: false,
      latency_ms: Math.round(performance.now() - started),
      error_type: error?.name || 'Error',
    };
  }
}

function openAIEndpoint(base) {
  const root = String(base || '').replace(/\/$/, '');
  if (root.endsWith('/chat/completions')) return root;
  if (root.endsWith('/v1') || root.endsWith('/openai')) return `${root}/chat/completions`;
  return `${root}/v1/chat/completions`;
}

async function openAICompletion(key, base, model) {
  const response = await fetch(openAIEndpoint(base), {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model, messages: [{ role: 'user', content: '只回复 OK' }],
      max_tokens: 8, temperature: 0, stream: false,
    }),
    signal: timeout(25_000),
  });
  const data = await jsonBody(response);
  return {
    live: response.ok && Boolean(data?.choices?.[0]?.message?.content),
    http_status: response.status,
    response_shape: Boolean(data?.choices),
  };
}

const tinyPng = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=';
const publicPhoto = 'https://upload.wikimedia.org/wikipedia/commons/3/3f/Fronalpstock_big.jpg';

const jobs = [
  probe('makers_ai_gateway', ['AI_GATEWAY_API_KEY', 'AI_GATEWAY_BASE_URL'], () => (
    openAICompletion(env.AI_GATEWAY_API_KEY, env.AI_GATEWAY_BASE_URL, env.AI_GATEWAY_MODEL || '@makers/deepseek-v4-flash')
  )),
  probe('deepseek_direct', ['DEEPSEEK_API_KEY'], () => (
    openAICompletion(env.DEEPSEEK_API_KEY, env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com/v1', env.DEEPSEEK_MODEL || 'deepseek-chat')
  )),
  probe('wsa_searchpro', ['WSA_API_KEY'], async () => {
    const response = await fetch(`${String(env.WSA_BASE_URL || 'https://api.wsa.cloud.tencent.com').replace(/\/$/, '')}/SearchPro`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.WSA_API_KEY}`, 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ Query: '2026年7月 人工智能 最新进展' }),
      signal: timeout(25_000),
    });
    const data = await jsonBody(response);
    const pages = data?.Pages || data?.pages || data?.Data?.Pages || data?.data?.pages;
    return { live: response.ok && Boolean(data), http_status: response.status, result_count: Array.isArray(pages) ? pages.length : null };
  }),
  probe('hunyuan_vision', ['HUNYUAN_IMAGE_API_KEY'], async () => {
    const response = await fetch('https://tokenhub.tencentmaas.com/v1/chat/completions', {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.HUNYUAN_IMAGE_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: env.HUNYUAN_VISION_MODEL || 'hy-vision-2.0-instruct',
        messages: [{ role: 'user', content: [
          { type: 'text', text: '这张图是什么颜色？只回复颜色。' },
          { type: 'image_url', image_url: { url: publicPhoto } },
        ] }],
        max_tokens: 32, temperature: 0, stream: false,
      }),
      signal: timeout(30_000),
    });
    const data = await jsonBody(response);
    return {
      live: response.ok && Boolean(data?.choices?.[0]?.message?.content),
      http_status: response.status, response_shape: Boolean(data?.choices),
      provider_error_code: data?.error?.code || data?.code || null,
    };
  }),
  probe('cloudflare_token', ['CLOUDFLARE_WORKERS_AI_TOKEN'], async () => {
    const response = await fetch('https://api.cloudflare.com/client/v4/user/tokens/verify', {
      headers: { Authorization: `Bearer ${env.CLOUDFLARE_WORKERS_AI_TOKEN}` }, signal: timeout(20_000),
    });
    const data = await jsonBody(response);
    const active = data?.success === true && data?.result?.status === 'active';
    return { live: response.ok && active, http_status: response.status, active };
  }),
  probe('cloudflare_vision', ['CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_WORKERS_AI_TOKEN'], async () => {
    const model = env.CLOUDFLARE_VISION_MODEL || '@cf/meta/llama-3.2-11b-vision-instruct';
    const response = await fetch(`https://api.cloudflare.com/client/v4/accounts/${env.CLOUDFLARE_ACCOUNT_ID}/ai/run/${model}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.CLOUDFLARE_WORKERS_AI_TOKEN}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: [{ role: 'user', content: '图片是什么颜色？只回答颜色。' }], image: tinyPng, max_tokens: 32, stream: false }),
      signal: timeout(30_000),
    });
    const data = await jsonBody(response);
    return {
      live: response.ok && data?.success === true && Boolean(data?.result?.response),
      http_status: response.status, response_shape: Boolean(data?.result),
      provider_error_codes: Array.isArray(data?.errors) ? data.errors.map((item) => item?.code).filter(Boolean).slice(0, 4) : [],
    };
  }),
  probe('tencent_map_server', ['TENCENT_MAP_SERVER_KEY'], async () => {
    const url = new URL('https://apis.map.qq.com/ws/place/v1/search');
    url.searchParams.set('key', env.TENCENT_MAP_SERVER_KEY);
    url.searchParams.set('keyword', '故宫博物院');
    url.searchParams.set('boundary', 'region(北京,0)');
    url.searchParams.set('page_size', '3');
    const response = await fetch(url, { signal: timeout(20_000) });
    const data = await jsonBody(response);
    return {
      live: response.ok && Number(data?.status) === 0 && Array.isArray(data?.data) && data.data.length > 0,
      http_status: response.status, provider_status: data?.status,
      result_count: Array.isArray(data?.data) ? data.data.length : 0,
    };
  }),
  probe('tencent_map_browser_key', ['VITE_TENCENT_MAP_KEY'], async () => {
    const url = new URL('https://apis.map.qq.com/ws/place/v1/search');
    url.searchParams.set('key', env.VITE_TENCENT_MAP_KEY);
    url.searchParams.set('keyword', '故宫博物院');
    url.searchParams.set('boundary', 'region(北京,0)');
    url.searchParams.set('page_size', '1');
    const response = await fetch(url, { signal: timeout(20_000) });
    const data = await jsonBody(response);
    return { live: response.ok && Number(data?.status) === 0, http_status: response.status, provider_status: data?.status };
  }),
  probe('tencent_meeting_mcp', ['TENCENT_MEETING_TOKEN'], async () => {
    const response = await fetch(env.TENCENT_MEETING_MCP_URL || 'https://mcp.meeting.tencent.com/mcp/wemeet-open/v1', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json', Accept: 'application/json, text/event-stream',
        'X-Tencent-Meeting-Token': env.TENCENT_MEETING_TOKEN,
        'X-Skill-Version': env.TENCENT_MEETING_SKILL_VERSION || 'v1.0.11',
      },
      body: JSON.stringify({ jsonrpc: '2.0', method: 'tools/list', params: {}, id: 'health-check' }),
      signal: timeout(25_000),
    });
    const data = await jsonBody(response);
    const tools = data?.result?.tools;
    return {
      live: response.ok && Array.isArray(tools) && tools.length > 0,
      http_status: response.status, tool_count: Array.isArray(tools) ? tools.length : 0,
      has_schedule: Array.isArray(tools) && tools.some((item) => String(item?.name || '').includes('schedule')),
    };
  }),
].filter((job, index) => selected([
  'makers_ai_gateway', 'deepseek_direct', 'wsa_searchpro', 'hunyuan_vision',
  'cloudflare_token', 'cloudflare_vision', 'tencent_map_server',
  'tencent_map_browser_key', 'tencent_meeting_mcp',
][index]));

const results = await Promise.all(jobs);

// These two calls validate the actual image model, not just the shared token.
if (selected('hunyuan_image')) results.push(await probe('hunyuan_image', ['HUNYUAN_IMAGE_API_KEY'], async () => {
  const response = await fetch('https://tokenhub.tencentmaas.com/v1/images/generations', {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.HUNYUAN_IMAGE_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: env.HUNYUAN_IMAGE_MODEL || 'hy-image-v3.0', prompt: '白底蓝色圆点，API 健康检查', size: '1024:1024', revise: 1 }),
    signal: timeout(90_000),
  });
  const data = await jsonBody(response);
  const image = data?.data?.[0]?.url || data?.data?.[0]?.b64_json || data?.images?.[0]?.url || data?.result?.image_url;
  return { live: response.ok && Boolean(image), http_status: response.status, response_shape: Boolean(image) };
}));

if (selected('cloudflare_image')) results.push(await probe('cloudflare_image', ['CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_WORKERS_AI_TOKEN'], async () => {
  const model = env.CLOUDFLARE_IMAGE_MODEL || '@cf/black-forest-labs/flux-1-schnell';
  const response = await fetch(`https://api.cloudflare.com/client/v4/accounts/${env.CLOUDFLARE_ACCOUNT_ID}/ai/run/${model}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.CLOUDFLARE_WORKERS_AI_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: 'a blue dot on a plain white background', steps: 4 }),
    signal: timeout(60_000),
  });
  const contentType = response.headers.get('content-type') || '';
  const body = new Uint8Array(await response.arrayBuffer());
  const imageLike = contentType.startsWith('image/') || (contentType.includes('application/json') && body.byteLength > 1000);
  return { live: response.ok && imageLike, http_status: response.status, content_type: contentType.split(';')[0], bytes: body.byteLength };
}));

const unusedConfigured = [
  'HUNYUAN_API_KEY', 'CODEX_ENV_PROBE', 'PLACE_API_TOKEN', 'DATABASE_URL',
  'DATABASE_SSL', 'EDGEONE_BLOB_STORE', 'LEGACY_BACKEND_URL',
].filter(configured);

console.log(JSON.stringify({ checked_at: new Date().toISOString(), results, unused_configured: unusedConfigured }, null, 2));
