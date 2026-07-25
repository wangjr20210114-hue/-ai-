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

function answerOf(events) {
  return events
    .filter((event) => event?.type === 'ai_response')
    .map((event) => String(event.content || ''))
    .join('');
}

async function chat(index, input) {
  const conversationId = `yb7_smoke_route_${runStamp}_${index}`;
  const startedAt = Date.now();
  const response = await fetch(endpoint('/chat'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify({
      message: input.message,
      response_language: 'zh-CN',
      ...(input.current_location ? { current_location: input.current_location } : {}),
    }),
  });
  const body = await response.text();
  if (!response.ok) throw new Error(`${input.id}: HTTP ${response.status} ${body.slice(0, 300)}`);
  const events = parseEvents(body);
  const mapAction = actionOf(events, 'map_action');
  const calendarAction = actionOf(events, 'calendar_action');
  const clarification = actionOf(events, 'clarification_action');
  const clarificationFields = clarification?.clarification?.fields || [];
  const answer = answerOf(events);
  const result = {
    id: input.id,
    conversation_id: conversationId,
    duration_ms: Date.now() - startedAt,
    event_types: [...new Set(events.map((event) => event?.type).filter(Boolean))],
    route_mode: mapAction?.action?.payload?.route_mode || '',
    route_strategy: mapAction?.action?.payload?.route_strategy || '',
    places: (mapAction?.action?.payload?.places || []).map((place) => place?.name).filter(Boolean),
    has_map_action: Boolean(mapAction),
    has_calendar_action: Boolean(calendarAction),
    has_clarification: Boolean(clarification),
    clarification_field_types: clarificationFields.map((field) => field?.type).filter(Boolean),
    clarification_option_counts: clarificationFields.map((field) => (field?.options || []).length),
    answer_preview: answer.slice(0, 180),
  };
  process.stderr.write(`${JSON.stringify(result)}\n`);
  try {
    input.assert(result);
  } catch (error) {
    throw new Error(`${error.message}; conversation_id=${conversationId}; result=${JSON.stringify(result)}`);
  }
  return result;
}

const location = {
  latitude: 39.9042,
  longitude: 116.4074,
  accuracy_meters: 20,
  captured_at: Date.now(),
  coordinate_type: 'wgs84',
};

const cases = [
  {
    id: 'current-location-walking',
    message: '我想步行去故宫博物院。浏览器定位已授权，请直接规划，不要询问起点。',
    current_location: location,
    assert(result) {
      if (!result.has_map_action || result.route_mode !== 'walking') {
        throw new Error(`${result.id}: expected a walking map action`);
      }
      if (!result.places.includes('当前位置')) {
        throw new Error(`${result.id}: current location was not retained as origin`);
      }
      if (result.route_strategy !== 'time_then_cost') {
        throw new Error(`${result.id}: expected the default time_then_cost strategy`);
      }
    },
  },
  {
    id: 'explicit-transit',
    message: '从北京站坐公交去故宫博物院，请规划真实路线。',
    assert(result) {
      if (!result.has_map_action || result.route_mode !== 'transit') {
        throw new Error(`${result.id}: expected a transit map action`);
      }
    },
  },
  {
    id: 'evidence-typo',
    message: '从北京站步行去天安们（这里有一个错别字），请按地点服务证据处理。',
    assert(result) {
      if (!result.has_map_action || result.route_mode !== 'walking' || !result.places.includes('天安门')) {
        throw new Error(`${result.id}: expected Tencent-backed correction to 天安门`);
      }
    },
  },
  {
    id: 'insufficient-evidence',
    message: '从北京站步行去不存在的测试地点咕咕塔XYZ，请不要猜坐标。',
    assert(result) {
      if (!result.has_clarification) {
        throw new Error(`${result.id}: expected a clarification instead of an invented route`);
      }
    },
  },
  {
    id: 'calendar-unique-typo',
    message: '请为我创建一条日程提案：2026年8月10日上午9点到10点去天安们参观。这里有一个明显错别字，请按地点服务证据处理。',
    assert(result) {
      if (!result.has_calendar_action || result.has_clarification) {
        throw new Error(`${result.id}: expected a calendar proposal without an extra question`);
      }
    },
  },
  {
    id: 'calendar-multiple-candidates',
    message: '请为我创建一条日程提案：2026年8月11日下午2点到3点去万达广场，但我还没有说城市。',
    assert(result) {
      if (
        !result.has_clarification
        || result.has_calendar_action
        || !result.clarification_field_types.includes('single')
        || Math.max(0, ...result.clarification_option_counts) < 2
      ) {
        throw new Error(`${result.id}: expected a finite place choice before calendar proposal`);
      }
    },
  },
  {
    id: 'calendar-no-candidate',
    message: '请为我创建一条日程提案：2026年8月12日上午9点到10点去不存在的日程地点咕咕塔XYZ。',
    assert(result) {
      if (
        !result.has_clarification
        || result.has_calendar_action
        || !result.clarification_field_types.includes('text')
      ) {
        throw new Error(`${result.id}: expected a fill-in clarification before calendar proposal`);
      }
    },
  },
];

const requestedCaseIds = new Set(
  String(process.env.FLORIS_SMOKE_CASES || '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean),
);
const selectedCases = requestedCaseIds.size
  ? cases.filter((item) => requestedCaseIds.has(item.id))
  : cases;
if (!selectedCases.length) {
  throw new Error(`No smoke cases matched FLORIS_SMOKE_CASES=${[...requestedCaseIds].join(',')}`);
}

const results = [];
for (let index = 0; index < selectedCases.length; index += 1) {
  results.push(await chat(index + 1, selectedCases[index]));
}
process.stdout.write(`${JSON.stringify({
  ok: true,
  base_url: baseUrl,
  run_stamp: runStamp,
  cases: results,
}, null, 2)}\n`);
