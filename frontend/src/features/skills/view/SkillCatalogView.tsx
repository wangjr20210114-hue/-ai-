import { Button, Tag } from 'tdesign-react';
import type { CSSProperties } from 'react';
import { CheckCircleIcon, RefreshIcon, SearchIcon } from 'tdesign-icons-react';

import type { InstalledSkill } from '../../../shared/types';
import type { SkillMarketplaceController } from './SkillsMarketplaceShell';

export function SkillCatalogView({
  controller,
}: {
  controller: SkillMarketplaceController;
}) {
  const {
    catalog, connections, disconnect, download, enabledCount, isInstalled,
    language, loading, query, refresh, save, saveConnection, savingId,
    setQuery, setTokenDrafts, skillName, skillText, t, tokenDrafts,
    view, visibleSkills,
  } = controller;

  return <>
    <section className="skills-page-hero">
      <div>
        <span className="skills-page-eyebrow">{t('skillsEyebrow')}</span>
        <h1>{view === 'installed' ? t('installedSkills') : t('composeSkills')}</h1>
        <p>{t('standardSkillsDescription')}</p>
      </div>
      <div className="skills-page-stat">
        <strong>{enabledCount}</strong><span>/ {catalog.length} {t('installed')}</span>
      </div>
    </section>
    <div className="skills-page-toolbar">
      <label>
        <SearchIcon aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('searchSkills')}
        />
      </label>
      <Button
        variant="outline"
        icon={<RefreshIcon />}
        loading={loading}
        onClick={() => void refresh()}
      >{t('refreshStatus')}</Button>
    </div>
    <section className="skills-page-grid">
      {visibleSkills.map((skill, index) => {
        const installed = isInstalled(skill);
        const connected = skill.configured;
        const connection = connections[skill.id];
        const missingRequired = (skill.requires || []).filter((id) => !isInstalled(
          catalog.find((item) => item.id === id) || { id } as InstalledSkill,
        ));
        return <article
          className={`skills-page-card ${installed ? 'is-installed' : ''}`}
          key={skill.id}
          style={{ '--skill-index': index } as CSSProperties}
        >
          <div className="skills-page-card-top">
            <span className="skills-page-card-icon" aria-hidden="true">{skill.icon}</span>
            <div>
              <div className="skills-page-card-title">
                <h2>{skillText(skill.name, skill.id)}</h2>
                {skill.publisher?.verified && <span title={t('verifiedPublisher')}><CheckCircleIcon /></span>}
              </div>
              <small>{t('skillPublisherVersion', {
                publisher: skill.publisher?.name || 'Floris',
                version: skill.version || '1.0.0',
              })}</small>
            </div>
            <Tag size="small" theme={skill.kind === 'system' ? 'primary' : 'default'}>
              {skill.kind === 'system' ? t('systemSkill') : t('communitySkill')}
            </Tag>
          </div>
          <p>{skillText(skill.description, '')}</p>
          <div className="skills-page-card-meta">
            <span>{skill.required_plan || 'free'}</span>
            <span>{t('componentApiCount', { count: (skill.component_actions || []).length })}</span>
            {skill.locked && <span>{t('alwaysOn')}</span>}
          </div>
          {!!skill.requires?.length && (
            <div className={`skill-dependency-note ${missingRequired.length ? 'is-blocked' : ''}`}>
              {t('requiresSkills', { names: skill.requires.map(skillName).join('、') })}
            </div>
          )}
          {skill.external && installed && skill.credential?.kind === 'token' && (
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
            {installed && (
              <button type="button" onClick={() => void download(skill.id)}>
                {t('downloadPackage')}
              </button>
            )}
            <Button
              size="small"
              theme={installed ? 'default' : 'primary'}
              variant={installed ? 'outline' : 'base'}
              disabled={skill.locked || loading}
              loading={savingId === skill.id}
              onClick={() => void save(skill, !installed)}
            >
              {skill.locked
                ? t('alwaysOn')
                : !skill.eligible && skill.eligibility_reason === 'login_required'
                  ? t('loginToInstall')
                  : installed ? t('uninstall') : t('install')}
            </Button>
          </div>
        </article>;
      })}
    </section>
  </>;
}
