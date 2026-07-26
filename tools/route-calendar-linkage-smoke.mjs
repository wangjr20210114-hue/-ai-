const baseUrl = String(process.env.FLORIS_SMOKE_BASE_URL || 'https://floris.jlutx.com').replace(/\/+$/, '');
const authQuery = String(process.env.FLORIS_SMOKE_AUTH_QUERY || '').replace(/^\?/, '');
const runStamp = Date.now();

function endpoint(path) {
  return `${baseUrl}${path}${authQuery ? `?${authQuery}` : ''}`;
}

function parseEvents(body) {
  const events = [];
  for (const frame of body.split(/\r?\n\r?\n/)) {
    const payload = frame.split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trim())
      .join('\n');
    if (!payload || payload === '[DONE]') continue;
    try { events.push(JSON.parse(payload)); } catch { /* Ignore heartbeat frames. */ }
  }
  return events;
}

function actionOf(events, type) {
  return events.find((event) => event?.type === type)?.payload;
}

function summarize(id, conversationId, durationMs, events) {
  const mapAction = actionOf(events, 'map_action');
  const calendarAction = actionOf(events, 'calendar_action');
  const clarificationAction = actionOf(events, 'clarification_action');
  const clarification = clarificationAction?.clarification;
  const places = mapAction?.action?.payload?.places || [];
  const changes = calendarAction?.action?.payload?.changes || [];
  const errorMessages = events
    .filter((event) => event?.type === 'error_message')
    .map((event) => event?.content || event?.payload?.message || event?.payload?.content || '')
    .filter(Boolean);
  const toolResults = events
    .filter((event) => event?.type === 'tool_result')
    .map((event) => ({
      name: event?.name || event?.payload?.name || '',
      content: event?.content || event?.payload?.content || '',
    }));
  return {
    id,
    conversation_id: conversationId,
    duration_ms: durationMs,
    event_types: [...new Set(events.map((event) => event?.type).filter(Boolean))],
    error_messages: errorMessages,
    tool_results: toolResults,
    has_map_action: Boolean(mapAction),
    has_calendar_action: Boolean(calendarAction),
    has_clarification: Boolean(clarification),
    route_mode: mapAction?.action?.payload?.route_mode || '',
    route_strategy: mapAction?.action?.payload?.route_strategy || '',
    ordered_places: places.map((place) => place?.name).filter(Boolean),
    route_plan_id: mapAction?.action?.payload?.route_plan_id || '',
    calendar_change_count: changes.length,
    calendar_source_route_plan_id: calendarAction?.action?.payload?.source_route_plan_id || '',
    clarification: clarification ? {
      id: clarification.id,
      title: clarification.title,
      fields: (clarification.fields || []).map((field) => ({
        id: field.id,
        label: field.label,
        type: field.type,
        options: field.options || [],
      })),
    } : null,
  };
}

async function chat(id, conversationId, body) {
  const startedAt = Date.now();
  const response = await fetch(endpoint('/chat'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify({ response_language: 'zh-CN', ...body }),
  });
  const responseBody = await response.text();
  if (!response.ok) {
    throw new Error(`${id}: HTTP ${response.status} ${responseBody.slice(0, 500)}`);
  }
  const result = summarize(id, conversationId, Date.now() - startedAt, parseEvents(responseBody));
  process.stderr.write(`${JSON.stringify(result)}\n`);
  return result;
}

function assert(condition, message, result) {
  if (!condition) {
    throw new Error(`${message}; result=${JSON.stringify(result)}`);
  }
}

async function answerClarification(id, conversationId, result, textReplacement = '北京天坛公园') {
  const clarification = result.clarification;
  const field = clarification?.fields?.[0];
  assert(field, `${id}: missing clarification field`, result);
  const value = field.type === 'single'
    ? field.options[0]
    : textReplacement;
  const responseId = `clarification-${clarification.id}-${Date.now()}`;
  return chat(id, conversationId, {
    activity: 'clarification_answered',
    message: `${field.label}：${value}`,
    text: `${field.label}：${value}`,
    message_id: responseId,
    client_message_id: responseId,
    interaction_mode: 'clarification',
    clarification_response: {
      id: clarification.id,
      source_message_id: `production-smoke-${clarification.id}`,
      answers: [{ id: field.id, label: field.label, value }],
    },
    reference_images: [],
  });
}

function mixedTextReplacement(result) {
  const label = result.clarification?.fields?.[0]?.label || '';
  if (label.includes('第 5 站')) {
    return '中国人民解放军总医院第一医学中心';
  }
  if (label.includes('终点')) {
    return '北京西站';
  }
  return '北京天坛公园';
}

const baseInstruction = [
  '请严格保持我给出的地点顺序，使用腾讯地图规划真实公交路线，并生成待确认的日程提案。',
  '日期是2026年8月22日，09:00出发；每个游览地点安排45分钟，站间按真实公交耗时顺延。',
  '不要直接写入日程；地点不确定时必须先按地图证据让我选择或填写。',
].join('');

const results = [];
const selectedScenario = String(process.env.FLORIS_LINKAGE_SCENARIO || '').trim();

if (!selectedScenario || selectedScenario === 'clean') {
  const conversationId = `yb7_linkage_${runStamp}_clean`;
  let result = await chat('six-stops-clean-with-typos', conversationId, {
    message: `${baseInstruction}依次为：北京站、天安们、故宫博物院、景山公园、北海公园、北京西站。`,
  });
  let proactiveClarificationCount = 0;
  for (let turn = 2; result.has_clarification && turn <= 8; turn += 1) {
    const field = result.clarification.fields[0];
    const options = field?.options || [];
    proactiveClarificationCount += 1;
    assert(
      field?.type === 'text' || (field?.type === 'single' && options.length >= 1),
      'proactive fallback should always give the user an actionable field',
      result,
    );
    if (
      field?.type === 'single'
      && options.some((option) => option.includes('北京市'))
      && options.some((option) => !option.includes('北京市'))
    ) {
      assert(
        options[0].includes('北京市'),
        'proven-city candidate should be first in the proactive card',
        result,
      );
    }
    result = await answerClarification(
      `six-stops-clean-turn-${turn}`,
      conversationId,
      result,
    );
  }
  assert(result.has_map_action, 'clean six-stop trip should produce a map action', result);
  assert(result.has_calendar_action, 'clean six-stop trip should produce a calendar proposal', result);
  assert(!result.has_clarification, 'resolved clean trip should not leave an open clarification', result);
  assert(proactiveClarificationCount <= 6, 'proactive fallback should converge without an excessive clarification loop', result);
  assert(result.route_mode === 'transit', 'explicit transit request should be retained', result);
  assert(result.route_strategy === 'time_then_cost', 'default route strategy should be time_then_cost', result);
  assert(result.ordered_places.length === 6, 'route should retain all six ordered places', result);
  assert(result.calendar_change_count >= 6, 'calendar proposal should retain every route stop', result);
  assert(
    result.calendar_source_route_plan_id === result.route_plan_id,
    'calendar proposal should reference the verified route plan',
    result,
  );
  results.push(result);
}

if (!selectedScenario || selectedScenario === 'ambiguous') {
  const conversationId = `yb7_linkage_${runStamp}_ambiguous`;
  const result = await chat('six-stops-ambiguous-place', conversationId, {
    message: `${baseInstruction}依次为：北京站、天安门、故宫博物院、万达广场、北海公园、北京西站。`,
  });
  assert(result.has_clarification, 'ambiguous place should require clarification', result);
  assert(!result.has_map_action && !result.has_calendar_action, 'ambiguous place must block route and calendar actions', result);
  assert(result.clarification.fields.some((field) => field.type === 'single' && field.options.length >= 2), 'ambiguous place should use a finite choice', result);
  results.push(result);
}

if (!selectedScenario || selectedScenario === 'missing') {
  const conversationId = `yb7_linkage_${runStamp}_missing`;
  let result = await chat('six-stops-missing-place', conversationId, {
    message: `${baseInstruction}依次为：北京站、天安门、故宫博物院、景山公园、北海公园、咕咕塔XYZ。`,
  });
  assert(result.has_clarification, 'unknown place should require clarification', result);
  assert(!result.has_map_action && !result.has_calendar_action, 'unknown place must block route and calendar actions', result);
  let sawTextFill = result.clarification.fields.some((field) => field.type === 'text');
  for (let turn = 2; !sawTextFill && result.has_clarification && turn <= 8; turn += 1) {
    result = await answerClarification(
      `six-stops-missing-turn-${turn}`,
      conversationId,
      result,
      mixedTextReplacement(result),
    );
    sawTextFill = Boolean(
      result.clarification?.fields?.some((field) => field.type === 'text'),
    );
  }
  assert(sawTextFill, 'unknown place should eventually use a text fill-in', result);
  results.push(result);
}

if (!selectedScenario || selectedScenario === 'mixed') {
  const conversationId = `yb7_linkage_${runStamp}_mixed`;
  let result = await chat('six-stops-mixed-turn-1', conversationId, {
    message: `${baseInstruction}依次为：北京站、天安们、故宫博物院、万达广场、北京301医元、咕咕塔XYZ。`,
  });
  const clarificationTypes = [];
  for (let turn = 2; result.has_clarification && turn <= 8; turn += 1) {
    clarificationTypes.push(...result.clarification.fields.map((field) => field.type));
    result = await answerClarification(
      `six-stops-mixed-turn-${turn}`,
      conversationId,
      result,
      mixedTextReplacement(result),
    );
  }
  assert(clarificationTypes.includes('single'), 'mixed trip should expose at least one finite place choice', result);
  assert(clarificationTypes.includes('text'), 'mixed trip should expose at least one fill-in for an unknown place', result);
  assert(result.has_map_action, 'resolved mixed trip should eventually produce a map action', result);
  assert(result.has_calendar_action, 'resolved mixed trip should eventually produce a calendar proposal', result);
  assert(result.ordered_places.length === 6, 'resolved mixed trip should retain all six places', result);
  assert(result.calendar_change_count >= 6, 'resolved mixed trip should retain six calendar changes', result);
  assert(
    result.calendar_source_route_plan_id === result.route_plan_id,
    'resolved mixed calendar proposal should stay linked to its route plan',
    result,
  );
  results.push(result);
}

process.stdout.write(`${JSON.stringify({
  ok: true,
  base_url: baseUrl,
  run_stamp: runStamp,
  cases: results,
}, null, 2)}\n`);
