import { describe, expect, it } from 'vitest';
import { assistantChainPositions } from './assistantMessageChain';

describe('assistant message chain', () => {
  it('joins consecutive assistant checkpoints into one visible answer', () => {
    expect(assistantChainPositions([
      { role: 'user' },
      { role: 'ai' },
      { role: 'ai' },
      { role: 'ai' },
      { role: 'user' },
      { role: 'ai' },
    ])).toEqual(['single', 'start', 'middle', 'end', 'single', 'single']);
  });

  it('does not join normal user and assistant turns', () => {
    expect(assistantChainPositions([
      { role: 'user' },
      { role: 'ai' },
      { role: 'user' },
      { role: 'ai' },
    ])).toEqual(['single', 'single', 'single', 'single']);
  });
});
