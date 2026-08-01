import { Button, Tag } from 'tdesign-react';
import { AppIcon } from 'tdesign-icons-react';
import { createPortal } from 'react-dom';
import { useSkillMarketplaceController } from '../../features/skills/controller/useSkillMarketplaceController';
import type { MarketplaceView } from '../../features/skills/model';
import type { InstalledSkill } from '../../shared/types';

export default function SkillsMarketplaceButton() {
  const controller = useSkillMarketplaceController();
  const {
    catalog, closeMarketplace, connections, disconnect, download, enabledCount, isInstalled,
    language, loading, login, marketplace, openMarketplace, query, refresh,
    save, saveConnection, savingId, setQuery, setTokenDrafts, setView,
    skillName, skillText, t, tokenDrafts, upload, uploadRef,
    uploads, view, visible, visibleSkills, wechatAvailable,
  } = controller;

  return <>
    <Button
      data-onboarding="skills"
      className="sidebar-settings-button"
      block
      variant="text"
      icon={<AppIcon />}
      loading={loading && !visible}
      onClick={() => void openMarketplace()}
    >{t('skillsMarketplace')}</Button>
    {visible && typeof document !== 'undefined' && createPortal(
      <div className="skills-page" role="dialog" aria-modal="true" aria-label={t('skillsMarketplace')}>
        <header className="skills-page-header">
          <button
            type="button"
            className="skills-page-back"
            onClick={(event) => {
              event.stopPropagation();
              closeMarketplace();
            }}
          >
            <span aria-hidden="true">←</span>{t('backToMain')}
          </button>
          <div className="skills-page-brand">
            <span className="skills-page-logo" aria-hidden="true">{t('skillLogoGlyph')}</span>
            <div><strong>{t('skillsMarketplace')}</strong><small>{t('standardSkillsSubtitle')}</small></div>
          </div>
          <div className="skills-page-account">
            <Tag theme="primary" variant="light">
              {marketplace?.entitlements.plan || t('guestPlan')}
            </Tag>
            <span>{marketplace?.identity.display_name || t('guestUser')}</span>
            {marketplace?.identity.auth_type === 'guest' && (
              <Button size="small" theme="primary" onClick={login}>
                {t('wechatLogin')}
              </Button>
            )}
          </div>
        </header>

        <div className="skills-page-layout">
          <aside className="skills-page-nav">
            {([
              ['catalog', t('allSkills'), '◇'],
              ['installed', t('installedSkills'), '✓'],
              ['dependencies', t('dependencyGraph'), '⌘'],
              ['docs', t('componentApiDocs'), '</>'],
              ['upload', t('uploadSkill'), '↑'],
            ] as Array<[MarketplaceView, string, string]>).map(([id, label, icon]) => (
              <button
                type="button"
                key={id}
                className={view === id ? 'is-active' : ''}
                onClick={() => setView(id)}
              ><span aria-hidden="true">{icon}</span>{label}</button>
            ))}
            <div className="skills-page-nav-note">
              <strong>{t('makersNative')}</strong>
              <span>{t('makersNativeSkillNote')}</span>
            </div>
          </aside>

          <main className="skills-page-main" aria-busy={loading}>
            {(view === 'catalog' || view === 'installed') && <>
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
                  <span aria-hidden="true">⌕</span>
                  <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t('searchSkills')} />
                </label>
                <Button variant="outline" loading={loading} onClick={() => void refresh()}>{t('refreshStatus')}</Button>
              </div>
              <section className="skills-page-grid">
                {visibleSkills.map((skill) => {
                  const installed = isInstalled(skill);
                  const connected = skill.configured;
                  const connection = connections[skill.id];
                  const missingRequired = (skill.requires || []).filter((id) => !isInstalled(
                    catalog.find((item) => item.id === id) || { id } as InstalledSkill,
                  ));
                  return <article className={`skills-page-card ${installed ? 'is-installed' : ''}`} key={skill.id}>
                    <div className="skills-page-card-top">
                      <span className="skills-page-card-icon" aria-hidden="true">{skill.icon}</span>
                      <div>
                        <div className="skills-page-card-title">
                          <h2>{skillText(skill.name, skill.id)}</h2>
                          {skill.publisher?.verified && <span title={t('verifiedPublisher')}>✓</span>}
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
                      <span>{t('componentApiCount', {
                        count: (skill.component_actions || []).length,
                      })}</span>
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
                        disabled={skill.locked
                          || loading
                          || (!skill.eligible
                            && skill.eligibility_reason === 'login_required'
                            && !wechatAvailable)}
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
            </>}

            {view === 'dependencies' && (
              <section className="skills-page-section">
                <span className="skills-page-eyebrow">{t('dependencyEyebrow')}</span>
                <h1>{t('dependencyGraph')}</h1>
                <p>{t('dependencyGraphHint')}</p>
                <div className="skill-graph">
                  {(marketplace?.dependency_graph.nodes || []).map((node) => {
                    const outgoing = marketplace?.dependency_graph.edges.filter((edge) => edge.from === node.id) || [];
                    return <article key={node.id}>
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
            )}

            {view === 'docs' && (
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
                  {(marketplace?.component_api.actions || []).map((action) => <article key={action.id}>
                    <code>{action.id}</code>
                    <Tag size="small">{action.permission}</Tag>
                    <p>{action.description}</p>
                    <dl>{Object.entries(action.input).map(([name, type]) => <div key={name}><dt>{name}</dt><dd>{type}</dd></div>)}</dl>
                  </article>)}
                </div>
              </section>
            )}

            {view === 'upload' && (
              <section className="skills-page-section">
                <span className="skills-page-eyebrow">{t('userSkillsEyebrow')}</span>
                <h1>{t('uploadSkill')}</h1>
                <p>{t('uploadSkillHint')}</p>
                {marketplace?.identity.auth_type === 'guest' ? (
                  <div className="skills-login-gate">
                    <strong>{t('loginRequiredForSkills')}</strong>
                    <p>{t('loginSkillReason')}</p>
                    {wechatAvailable
                      ? <Button theme="primary" onClick={login}>{t('wechatLogin')}</Button>
                      : <small>{t('wechatLoginUnavailable')}</small>}
                  </div>
                ) : <>
                  <div className="skill-upload-drop">
                    <span aria-hidden="true">{t('skillZipGlyph')}</span>
                    <strong>{t('selectSkillZip')}</strong>
                    <small>{t('skillReviewPending')}</small>
                    <input
                      ref={uploadRef}
                      type="file"
                      accept=".zip,application/zip,application/x-zip-compressed"
                      onChange={(event) => void upload(event.target.files?.[0])}
                    />
                    <Button theme="primary" loading={savingId === 'upload'} onClick={() => uploadRef.current?.click()}>
                      {t('chooseFile')}
                    </Button>
                  </div>
                  <div className="skill-upload-list">
                    {uploads.map((item) => <article key={item.id}>
                      <div><strong>{item.name}</strong><small>{new Date(item.submitted_at).toLocaleString(language)}</small></div>
                      <Tag theme="warning">{t('pendingReview')}</Tag>
                    </article>)}
                    {!uploads.length && <p>{t('noSkillUploads')}</p>}
                  </div>
                </>}
              </section>
            )}
          </main>
        </div>
      </div>,
      document.body,
    )}
  </>;
}
