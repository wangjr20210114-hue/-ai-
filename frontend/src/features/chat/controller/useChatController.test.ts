import { describe, expect, it } from 'vitest';

import {
  reduceChatControllerEvent,
} from '../model/events';
import { initialChatControllerState } from '../model/state';
import type { RichMediaAsset } from '../../../types';


describe('chat controller event reduction', () => {
  it('reduces progress, answer text, and reviewed media independently', () => {
    const reviewedMedia = [{
      source_id: 'source-1',
      url: 'https://example.test/image.jpg',
      source_url: 'https://example.test/article',
      vision_reviewed: true,
    }] as RichMediaAsset[];
    const staged = reduceChatControllerEvent(initialChatControllerState, {
      type: 'stage',
      payload: { stage: 'searching' },
    });
    const tokenized = reduceChatControllerEvent(staged, {
      type: 'token',
      content: '答',
    });
    const withMedia = reduceChatControllerEvent(tokenized, {
      type: 'media',
      payload: { media: reviewedMedia },
    });
    expect(withMedia.progress.stage).toBe('searching');
    expect(withMedia.streamingText).toBe('答');
    expect(withMedia.search.media).toEqual(reviewedMedia);
  });

  it('ignores unknown and raw reasoning events', () => {
    const unknown = reduceChatControllerEvent(initialChatControllerState, {
      type: 'reasoning',
      reasoning_content: 'hidden',
    });
    expect(unknown).toBe(initialChatControllerState);
  });
});
