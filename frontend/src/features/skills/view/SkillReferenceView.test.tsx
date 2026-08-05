import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { SkillReferenceView } from './SkillReferenceView';
import type { SkillMarketplaceController } from './SkillsMarketplaceShell';

describe('SkillReferenceView', () => {
  it('starts with the secondary page navigation collapsed on desktop', () => {
    const controller = {
      marketplace: {
        component_api: { version: '2026-08-04', actions: [] },
      },
      skillText: (_value: unknown, fallback: string) => fallback,
      t: (key: string) => key,
    } as unknown as SkillMarketplaceController;

    const html = renderToStaticMarkup(
      <SkillReferenceView controller={controller} />,
    );

    expect(html).toContain('component-docs is-toc-collapsed');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('aria-label="componentDocsOnThisPage"');
  });
});
