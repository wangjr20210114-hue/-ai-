import { useMemo, useState } from 'react';
import { ChevronLeftIcon, ChevronRightIcon } from 'tdesign-icons-react';

import type { TranslationKey } from '../../../i18n';
import type { SkillComponentApi } from '../model';
import type { SkillMarketplaceController } from './SkillsMarketplaceShell';

const DOC_SECTIONS = [
  ['component-doc-overview', 'componentDocsOverview'],
  ['component-doc-quickstart', 'componentDocsQuickStart'],
  ['component-doc-contracts', 'componentDocsContracts'],
  ['component-doc-errors', 'componentDocsErrors'],
] as const;
const CLIENT_PLATFORMS = ['Web', 'HarmonyOS', 'Android', 'iOS'];
const QUICK_START_STEPS = ['componentDocsStepSession', 'componentDocsStepAction', 'componentDocsStepRender'] as const;
const ERROR_CODES = [
  ['INVALID_ACTION', 'componentDocsErrorAction'],
  ['INVALID_PAYLOAD', 'componentDocsErrorPayload'],
  ['PERMISSION_DENIED', 'componentDocsErrorPermission'],
  ['CONFLICT', 'componentDocsErrorConflict'],
] as const;
const CATEGORY_ORDER = ['chat', 'search', 'maps', 'calendar', 'paper', 'image', 'workspace'];
const CATEGORY_LABELS: Record<string, TranslationKey> = {
  chat: 'componentDocsCategoryChat',
  search: 'componentDocsCategorySearch',
  maps: 'componentDocsCategoryMaps',
  calendar: 'componentDocsCategoryCalendar',
  paper: 'componentDocsCategoryPaper',
  image: 'componentDocsCategoryImage',
  workspace: 'componentDocsCategoryWorkspace',
};

type ComponentAction = SkillComponentApi['actions'][number];

function actionExample(action: ComponentAction) {
  const examples: Record<string, Record<string, unknown>> = {
    'clarification.request': {
      action: action.id,
      payload: {
        clarification: {
          id: 'travel-budget',
          title: 'Budget preference',
          prompt: 'Which style fits this trip?',
          fields: [{ id: 'budget', label: 'Budget', type: 'single', options: ['Economy', 'Standard', 'Undecided'] }],
        },
      },
    },
    'search.evidence.publish': {
      action: action.id,
      payload: { source_id: 'source-01', title: 'Product announcement', url: 'https://example.com/news' },
    },
    'search.media.publish': {
      action: action.id,
      payload: { source_id: 'source-01', media: [{ url: 'https://example.com/photo.jpg', alt: 'Launch event' }] },
    },
    'maps.place.select': {
      action: action.id,
      payload: { places: [{ name: 'People Square', lat: 31.2304, lng: 121.4737 }] },
    },
    'calendar.change.propose': {
      action: action.id,
      payload: {
        changes: [{ operation: 'create', title: 'Project sync', start_at: '2026-08-03T10:00:00+08:00' }],
        warnings: [],
      },
    },
    'image.result.publish': {
      action: action.id,
      payload: { storage_key: 'images/result.png', versions: [{ label: 'Original' }] },
    },
    'paper.results.publish': {
      action: action.id,
      payload: { papers: [{ title: 'Attention Is All You Need', arxiv_id: '1706.03762' }], topic: 'Transformer' },
    },
    'workspace.action.propose': {
      action: action.id,
      payload: { kind: 'meeting_create', payload: { subject: 'Project sync', start_time: '2026-08-05T10:00:00+08:00' } },
    },
  };
  if (examples[action.id]) return examples[action.id];
  return {
    action: action.id,
    payload: Object.fromEntries((action.required || []).map((field) => [field, `<${action.input[field] || 'value'}>`])),
  };
}

function categoryAnchor(category: string) {
  return `component-doc-category-${category.replace(/[^a-z0-9-]/gi, '-')}`;
}

export function SkillReferenceView({
  controller,
}: {
  controller: SkillMarketplaceController;
}) {
  const { marketplace, skillText, t } = controller;
  const [tocCollapsed, setTocCollapsed] = useState(true);
  const actions = useMemo(
    () => marketplace?.component_api.actions || [],
    [marketplace?.component_api.actions],
  );
  const version = marketplace?.component_api.version || '';
  const groupedActions = useMemo(() => {
    const groups = new Map<string, ComponentAction[]>();
    actions.forEach((action) => {
      const category = action.category || 'other';
      groups.set(category, [...(groups.get(category) || []), action]);
    });
    return [...groups.entries()].sort(([left], [right]) => {
      const leftOrder = CATEGORY_ORDER.indexOf(left);
      const rightOrder = CATEGORY_ORDER.indexOf(right);
      return (leftOrder < 0 ? 99 : leftOrder) - (rightOrder < 0 ? 99 : rightOrder);
    });
  }, [actions]);
  const quickStart = JSON.stringify(actionExample(
    actions.find((action) => action.id === 'calendar.change.propose') || actions[0] || {
      id: 'calendar.change.propose',
      permission: 'components.calendar',
      description: '',
      input: {},
    },
  ), null, 2);

  return (
    <div className={`component-docs ${tocCollapsed ? 'is-toc-collapsed' : ''}`}>
      <aside className="component-docs-toc" aria-label={t('componentDocsOnThisPage')}>
        <button
          type="button"
          className="component-docs-toc-toggle"
          aria-expanded={!tocCollapsed}
          aria-label={t('componentDocsOnThisPage')}
          title={t('componentDocsOnThisPage')}
          onClick={() => setTocCollapsed((current) => !current)}
        >
          <strong>{t('componentDocsOnThisPage')}</strong>
          {tocCollapsed ? <ChevronRightIcon /> : <ChevronLeftIcon />}
        </button>
        <nav>
          {DOC_SECTIONS.map(([id, label]) => <a href={`#${id}`} key={id}>{t(label)}</a>)}
          <div className="component-docs-toc-groups">
            {groupedActions.map(([category]) => <a href={`#${categoryAnchor(category)}`} key={category}>
              {t(CATEGORY_LABELS[category] || 'componentDocsCategoryOther')}
            </a>)}
          </div>
        </nav>
      </aside>

      <article className="component-docs-content component-docs-markdown">
        <header className="component-docs-intro" id="component-doc-overview">
          <span className="skills-page-eyebrow">{t('componentApiEyebrow', { version })}</span>
          <h1>{t('componentApiDocs')}</h1>
          <p>{t('componentApiHint')}</p>
          <blockquote>{t('componentDocsPlatformManaged')}</blockquote>
          <p className="component-docs-platforms">
            <strong>{t('componentDocsPlatforms')}</strong><span>{CLIENT_PLATFORMS.join(' · ')}</span>
          </p>
          <dl className="component-docs-summary">
            <div><dt>{t('componentDocsVersion')}</dt><dd>{version}</dd></div>
            <div><dt>{t('componentDocsTransport')}</dt><dd>{t('componentDocsTransportValue')}</dd></div>
            <div><dt>{t('componentDocsActionCount')}</dt><dd>{actions.length}</dd></div>
          </dl>
        </header>

        <section className="component-docs-section" id="component-doc-quickstart">
          <h2>{t('componentDocsQuickStart')}</h2>
          <p>{t('componentDocsQuickStartHint')}</p>
          <ol>
            {QUICK_START_STEPS.map((step) => <li key={step}>{t(step)}</li>)}
          </ol>
          <h3>{t('componentDocsJson')}</h3>
          <div className="component-docs-code">
            <button type="button" onClick={() => void navigator.clipboard?.writeText(quickStart)}>{t('copy')}</button>
            <pre><code>{quickStart}</code></pre>
          </div>
          <blockquote>{t('componentDocsEnvelopeNote')}</blockquote>
        </section>

        <section className="component-docs-section" id="component-doc-contracts">
          <h2>{t('componentDocsContracts')}</h2>
          <p>{t('componentDocsContractsHint')}</p>
          <div className="component-api-list">
            {groupedActions.map(([category, categoryActions]) => <section
              className="component-api-category"
              id={categoryAnchor(category)}
              key={category}
            >
              <h3>{t(CATEGORY_LABELS[category] || 'componentDocsCategoryOther')}</h3>
              {categoryActions.map((action) => {
                const example = JSON.stringify(actionExample(action), null, 2);
                return <section className="component-api-entry" id={`component-action-${action.id}`} key={action.id}>
                  <h4>{skillText(action.name, action.id)}</h4>
                  <p><code>{action.id}</code></p>
                  <p>{skillText(action.description_i18n, action.description)}</p>
                  <table aria-label={t('componentDocsParameters')}>
                    <thead><tr><th>{t('componentDocsParameter')}</th><th>{t('componentDocsType')}</th><th>{t('componentDocsRequired')}</th></tr></thead>
                    <tbody>
                      {Object.entries(action.input).map(([name, type]) => <tr key={name}>
                        <td><code>{name}</code></td><td>{type}</td><td>{action.required?.includes(name) ? t('yes') : t('no')}</td>
                      </tr>)}
                    </tbody>
                  </table>
                  <h5>{t('componentDocsJson')}</h5>
                  <pre className="component-api-example"><code>{example}</code></pre>
                </section>;
              })}
            </section>)}
          </div>
        </section>

        <section className="component-docs-section" id="component-doc-errors">
          <h2>{t('componentDocsErrors')}</h2>
          <p>{t('componentDocsErrorsHint')}</p>
          <table className="component-docs-error-table">
            <tbody>{ERROR_CODES.map(([code, label]) => <tr key={code}><td><code>{code}</code></td><td>{t(label)}</td></tr>)}</tbody>
          </table>
        </section>

      </article>
    </div>
  );
}
