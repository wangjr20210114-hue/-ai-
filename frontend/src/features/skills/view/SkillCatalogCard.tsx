import { Button } from 'tdesign-react';
import type { CSSProperties } from 'react';
import { CheckCircleIcon } from 'tdesign-icons-react';

import type { TranslationKey } from '../../../i18n';
import type { InstalledSkill } from '../../../shared/types';
import type { SkillMarketplaceController } from './SkillsMarketplaceShell';

const PLAN_LABELS: Record<NonNullable<InstalledSkill['required_plan']>, TranslationKey> = {
  guest: 'skillPlanGuest',
  free: 'skillPlanFree',
  plus: 'skillPlanPlus',
  pro: 'skillPlanPro',
};

export function SkillCatalogCard({
  controller,
  index,
  skill,
}: {
  controller: SkillMarketplaceController;
  index: number;
  skill: InstalledSkill;
}) {
  const {
    catalog, connections, disconnect, download, isEnabled, language, loading,
    save, saveConnection, savingId, setTokenDrafts, skillName, skillText, t,
    tokenDrafts,
  } = controller;
  const enabled = isEnabled(skill);
  const connected = skill.configured;
  const connection = connections[skill.id];
  const missingRequired = (skill.requires || []).filter((id) => !isEnabled(
    catalog.find((item) => item.id === id) || { id } as InstalledSkill,
  ));
  const planLabel = t(PLAN_LABELS[skill.required_plan || 'free']);
  const relationText = (ids: string[], empty: string) => (
    ids.length ? ids.map(skillName).join('、') : empty
  );

  return <article
    className={`skills-page-card ${enabled ? 'is-enabled' : 'is-disabled'}`}
    style={{ '--skill-index': index } as CSSProperties}
  >
    <div className="skills-page-card-top">
      <span className="skills-page-card-icon" aria-hidden="true">{skill.icon}</span>
      <div>
        <div className="skills-page-card-title">
          <h3>{skillText(skill.name, skill.id)}</h3>
          {skill.publisher?.verified && <span title={t('verifiedPublisher')}><CheckCircleIcon /></span>}
        </div>
        <small>{t('skillPublisherVersion', {
          publisher: skill.publisher?.name || 'Floris',
          version: skill.version || '1.0.0',
        })}</small>
      </div>
      <span className={`skills-page-card-status ${enabled ? 'is-enabled' : ''}`}>
        {t(enabled ? 'skillEnabledStatus' : 'skillDisabledStatus')}
      </span>
    </div>
    <p>{skillText(skill.description, '')}</p>
    <div className="skills-page-card-meta">
      <span>{planLabel}</span>
      {!!skill.component_actions?.length && <span>{t('componentApiCount', { count: skill.component_actions.length })}</span>}
      {skill.locked && <span>{t('alwaysOn')}</span>}
    </div>
    <dl className={`skill-relations ${missingRequired.length ? 'has-missing' : ''}`}>
      <div>
        <dt>{t('skillDependencyLabel')}</dt>
        <dd>{relationText(skill.requires || [], t('noRequiredDependencies'))}</dd>
      </div>
      <div>
        <dt>{t('skillRecommendationLabel')}</dt>
        <dd>{relationText(skill.recommends || [], t('noRecommendations'))}</dd>
      </div>
      <div>
        <dt>{t('skillConflictLabel')}</dt>
        <dd>{relationText(skill.conflicts || [], t('noSkillConflicts'))}</dd>
      </div>
    </dl>
    {skill.external && enabled && skill.credential?.kind === 'token' && (
      <div className="skill-credential-region">
        {!connected ? <>
          <p>{skillText(skill.credential.instructions, '')}</p>
          <div className="skill-credential-editor">
            <input
              type="password"
              autoComplete="off"
              value={tokenDrafts[skill.id] || ''}
              placeholder={t('skillTokenPlaceholder')}
              onChange={(event) => setTokenDrafts((current) => ({
                ...current,
                [skill.id]: event.target.value,
              }))}
            />
            <Button size="small" loading={savingId === skill.id} onClick={() => void saveConnection(skill.id)}>
              {t('saveConnection')}
            </Button>
          </div>
        </> : <div className="skill-credential-connected">
          <span>{connection?.expires_at ? t('connectionExpiresAt', {
            time: new Date(connection.expires_at * 1000).toLocaleString(language),
          }) : t('connected')}</span>
          <button type="button" className="skill-install-link is-danger" onClick={() => void disconnect(skill.id)}>
            {t('disconnectSkill')}
          </button>
        </div>}
      </div>
    )}
    <div className="skills-page-card-actions">
      {skill.eligible && (
        <button type="button" onClick={() => void download(skill.id)}>
          {t('downloadPackage')}
        </button>
      )}
      <Button
        size="small"
        theme={enabled ? 'default' : 'primary'}
        variant={enabled ? 'outline' : 'base'}
        disabled={skill.locked || loading}
        loading={savingId === skill.id}
        onClick={() => void save(skill, !enabled)}
      >
        {skill.locked
          ? t('alwaysOn')
          : !skill.eligible && skill.eligibility_reason === 'login_required'
            ? t('loginToEnable')
            : t(enabled ? 'disableSkillAction' : 'enableSkillAction')}
      </Button>
    </div>
  </article>;
}
