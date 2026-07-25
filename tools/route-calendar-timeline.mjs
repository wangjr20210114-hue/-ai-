const baseUrl = String(
  process.env.FLORIS_SMOKE_BASE_URL || 'https://floris.jlutx.com',
).replace(/\/+$/, '');
const conversationId = `yb7_timeline_${Date.now()}`;
const startedAt = performance.now();
const events = [];

function elapsedMs() {
  return Math.round(performance.now() - startedAt);
}

function toolName(event) {
  return event?.payload?.name
    || event?.payload?.tool_name
    || event?.name
    || '';
}

function record(frame) {
  const payload = frame.split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())
    .join('\n');
  if (!payload || payload === '[DONE]') return;
  try {
    const event = JSON.parse(payload);
    const row = {
      elapsed_ms: elapsedMs(),
      type: event?.type || '',
      tool: toolName(event),
    };
    events.push(row);
    process.stderr.write(`${JSON.stringify(row)}\n`);
  } catch {
    // Heartbeats and non-JSON frames are not part of the public event contract.
  }
}

const coldScenario = String(process.env.FLORIS_TIMELINE_SCENARIO || '') === 'cold';
const message = coldScenario
  ? [
      '请严格保持我给出的地点顺序，使用腾讯地图规划真实公交路线，并生成待确认的日程提案。',
      '日期是2026年8月13日，08:30出发；每个游览地点安排40分钟，站间按真实公交耗时顺延。',
      '不要直接写入日程；地点不确定时必须先按地图证据让我选择或填写。',
      '依次为：颐和园、圆明园遗址公园、清华大学艺术博物馆、国家体育场鸟巢、雍和宫、北京站。',
    ].join('')
  : [
      '请严格保持我给出的地点顺序，使用腾讯地图规划真实公交路线，并生成待确认的日程提案。',
      '日期是2026年8月12日，09:00出发；每个游览地点安排45分钟，站间按真实公交耗时顺延。',
      '不要直接写入日程；地点不确定时必须先按地图证据让我选择或填写。',
      '依次为：北京站、天安们、故宫博物院、景山公园、北海公园、北京西站。',
    ].join('');

const response = await fetch(`${baseUrl}/chat`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'makers-conversation-id': conversationId,
  },
  body: JSON.stringify({
    message,
    response_language: 'zh-CN',
  }),
});
if (!response.ok || !response.body) {
  throw new Error(`HTTP ${response.status}: ${(await response.text()).slice(0, 500)}`);
}

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const frames = buffer.split(/\r?\n\r?\n/);
  buffer = frames.pop() || '';
  for (const frame of frames) record(frame);
}
buffer += decoder.decode();
if (buffer.trim()) record(buffer);

process.stdout.write(`${JSON.stringify({
  base_url: baseUrl,
  conversation_id: conversationId,
  total_ms: elapsedMs(),
  events,
}, null, 2)}\n`);
