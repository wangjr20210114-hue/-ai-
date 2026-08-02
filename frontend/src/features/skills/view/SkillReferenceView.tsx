import { Tag } from 'tdesign-react';
import type { CSSProperties } from 'react';

import type { SkillMarketplaceController } from './SkillsMarketplaceShell';

export function SkillReferenceView({
  controller,
}: {
  controller: SkillMarketplaceController;
}) {
  const { marketplace, skillName, skillText, t, view } = controller;
  if (view === 'dependencies') {
    return (
      <section className="skills-page-section">
        <span className="skills-page-eyebrow">{t('dependencyEyebrow')}</span>
        <h1>{t('dependencyGraph')}</h1>
        <p>{t('dependencyGraphHint')}</p>
        <div className="skill-graph">
          {(marketplace?.dependency_graph.nodes || []).map((node, index) => {
            const outgoing = marketplace?.dependency_graph.edges.filter((edge) => edge.from === node.id) || [];
            return <article key={node.id} style={{ '--skill-index': index } as CSSProperties}>
              <div className="skill-graph-node">
                <strong>{skillText(node.name, node.id)}</strong>
                <small>{node.id} · {node.required_plan}</small>
              </div>
              <div className="skill-graph-edges">
                {outgoing.map((edge) => <div key={`${edge.from}-${edge.to}-${edge.type}`} className={edge.type}>
                  <span>{edge.type === 'requires'
                    ? t('requiredDependencyEdge')
                    : t('recommendedDependencyEdge')}</span>
                  <b>{skillName(edge.to)}</b>
                </div>)}
                {!outgoing.length && <span>{t('noDependencies')}</span>}
              </div>
            </article>;
          })}
        </div>
      </section>
    );
  }

  return (
    <section className="skills-page-section">
      <span className="skills-page-eyebrow">{t('componentApiEyebrow', {
        version: marketplace?.component_api.version || '',
      })}</span>
      <h1>{t('componentApiDocs')}</h1>
      <p>{t('componentApiHint')}</p>
      <div className="component-api-security">
        <b>{t('securityBoundary')}</b>
        <span>{t('componentApiSecurity')}</span>
      </div>
      <div className="component-api-list">
        {(marketplace?.component_api.actions || []).map((action, index) => <article
          key={action.id}
          style={{ '--skill-index': index } as CSSProperties}
        >
          <code>{action.id}</code>
          <Tag size="small">{action.permission}</Tag>
          <p>{action.description}</p>
          <dl>{Object.entries(action.input).map(([name, type]) => <div key={name}><dt>{name}</dt><dd>{type}</dd></div>)}</dl>
        </article>)}
      </div>
    </section>
  );
}
