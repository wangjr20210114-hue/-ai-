import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { ChatMessage } from '../model';
import type { WorkspaceAction } from '../model';
import { selectRenderer } from './renderers/rendererRegistry';
import { WorkspaceActionRenderer } from './renderers/WorkspaceActionRenderer';


function message(values: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 'message-1',
    role: 'ai',
    content: 'answer',
    ts: 1,
    ...values,
  };
}

describe('message renderer registry', () => {
  it('uses deterministic structured priority and a text fallback', () => {
    const search = message({
      searchResults: {
        query: 'q',
        results: [],
        images: [],
        media: [],
        sources_used: [],
        total: 0,
      },
      papers: [{ title: 'paper' } as NonNullable<ChatMessage['papers']>[number]],
    });
    expect(selectRenderer(search).id).toBe('search-evidence');
    expect(selectRenderer(message({
      papers: [{ title: 'paper' } as NonNullable<ChatMessage['papers']>[number]],
    })).id).toBe('paper');
    expect(selectRenderer(message()).id).toBe('text');
  });

  it('renders an expired map status instead of a stale action button', () => {
    const action = {
      schema_version: 1,
      id: 'expired-map',
      kind: 'map_recommendation',
      status: 'failed',
      version: 1,
      payload: { action_text: 'Open stale route', calendar_offer: true },
    } satisfies WorkspaceAction;

    const html = renderToStaticMarkup(<WorkspaceActionRenderer
      actions={[action]}
      busyKey=""
      conversationId="conversation-1"
      generationActive={false}
      onAction={async () => undefined}
      onRouteCalendarProposal={async () => undefined}
      onReplace={() => undefined}
      renderMeeting={() => null}
    />);

    expect(html).toContain('这项操作已失效，请重新生成');
    expect(html).not.toContain('<button');
    expect(html).not.toContain('Open stale route');
  });
});
