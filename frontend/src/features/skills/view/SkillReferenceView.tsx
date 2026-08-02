import { Tag } from 'tdesign-react';
import type { CSSProperties } from 'react';

import type { SkillMarketplaceController } from './SkillsMarketplaceShell';

const DOC_SECTIONS = [
  ['component-doc-overview', 'componentDocsOverview'],
  ['component-doc-quickstart', 'componentDocsQuickStart'],
  ['component-doc-contracts', 'componentDocsContracts'],
  ['component-doc-errors', 'componentDocsErrors'],
  ['component-doc-security', 'securityBoundary'],
] as const;
const CLIENT_PLATFORMS = ['Web', 'HarmonyOS', 'Android', 'iOS'];
const QUICK_START_STEPS = ['componentDocsStepSession', 'componentDocsStepAction', 'componentDocsStepRender'] as const;
const ERROR_CODES = [
  ['INVALID_ACTION', 'componentDocsErrorAction'],
  ['INVALID_PAYLOAD', 'componentDocsErrorPayload'],
  ['PERMISSION_DENIED', 'componentDocsErrorPermission'],
  ['CONFLICT', 'componentDocsErrorConflict'],
] as const;

export function SkillReferenceView({
  controller,
}: {
  controller: SkillMarketplaceController;
}) {
  const { marketplace, skillText, t } = controller;
  const actions = marketplace?.component_api.actions || [];
  const version = marketplace?.component_api.version || '';
  const quickStart = `{
  "action": "calendar.change.propose",
  "payload": { "changes": [] }
}`;

  return (
    <div className="component-docs">
      <aside className="component-docs-toc" aria-label={t('componentDocsOnThisPage')}>
        <strong>{t('componentDocsOnThisPage')}</strong>
        {DOC_SECTIONS.map(([id, label]) => <a href={`#${id}`} key={id}>{t(label)}</a>)}
      </aside>

      <article className="component-docs-content">
        <section className="component-docs-intro" id="component-doc-overview">
          <span className="skills-page-eyebrow">{t('componentApiEyebrow', { version })}</span>
          <h1>{t('componentApiDocs')}</h1>
          <p>{t('componentApiHint')}</p>
          <div className="component-docs-platforms" aria-label={t('componentDocsPlatforms')}>
            {CLIENT_PLATFORMS.map((platform) => <span key={platform}>{platform}</span>)}
          </div>
          <div className="component-docs-summary">
            <div><small>{t('componentDocsVersion')}</small><strong>{version}</strong></div>
            <div><small>{t('componentDocsTransport')}</small><strong>{t('componentDocsTransportValue')}</strong></div>
            <div><small>{t('componentDocsActionCount')}</small><strong>{actions.length}</strong></div>
          </div>
        </section>

        <section className="component-docs-section" id="component-doc-quickstart">
          <div className="component-docs-heading"><span>{'01'}</span><div><h2>{t('componentDocsQuickStart')}</h2><p>{t('componentDocsQuickStartHint')}</p></div></div>
          <ol className="component-docs-steps">
            {QUICK_START_STEPS.map((step, index) => <li key={step}><b>{index + 1}</b><span>{t(step)}</span></li>)}
          </ol>
          <div className="component-docs-code"><div><span>{t('componentDocsJson')}</span><button type="button" onClick={() => void navigator.clipboard?.writeText(quickStart)}>{t('copy')}</button></div><pre><code>{quickStart}</code></pre></div>
          <p className="component-docs-note">{t('componentDocsEnvelopeNote')}</p>
        </section>

        <section className="component-docs-section" id="component-doc-contracts">
          <div className="component-docs-heading"><span>{'02'}</span><div><h2>{t('componentDocsContracts')}</h2><p>{t('componentDocsContractsHint')}</p></div></div>
          <div className="component-api-list">
            {actions.map((action, index) => <article
              key={action.id}
              style={{ '--skill-index': index } as CSSProperties}
            >
              <header><div><small>{action.category || 'component'}</small><h3>{skillText(action.name, action.id)}</h3></div><Tag size="small">{action.permission}</Tag></header>
              <code>{action.id}</code>
              <p>{skillText(action.description_i18n, action.description)}</p>
              <div className="component-api-table" role="table" aria-label={t('componentDocsParameters')}>
                <div role="row"><b role="columnheader">{t('componentDocsParameter')}</b><b role="columnheader">{t('componentDocsType')}</b><b role="columnheader">{t('componentDocsRequired')}</b></div>
                {Object.entries(action.input).map(([name, type]) => <div role="row" key={name}><code role="cell">{name}</code><span role="cell">{type}</span><span role="cell">{action.required?.includes(name) ? t('yes') : t('no')}</span></div>)}
              </div>
            </article>)}
          </div>
        </section>

        <section className="component-docs-section" id="component-doc-errors">
          <div className="component-docs-heading"><span>{'03'}</span><div><h2>{t('componentDocsErrors')}</h2><p>{t('componentDocsErrorsHint')}</p></div></div>
          <div className="component-docs-error-table">
            {ERROR_CODES.map(([code, label]) => <div key={code}><code>{code}</code><span>{t(label)}</span></div>)}
          </div>
        </section>

        <section className="component-docs-section" id="component-doc-security">
          <div className="component-docs-heading"><span>{'04'}</span><div><h2>{t('securityBoundary')}</h2><p>{t('componentApiSecurity')}</p></div></div>
          <div className="component-api-security">
            <b>{t('componentDocsClientRule')}</b>
            <span>{t('componentDocsClientRuleHint')}</span>
          </div>
        </section>
      </article>
    </div>
  );
}
