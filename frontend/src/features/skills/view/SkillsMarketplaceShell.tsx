import { Button, Tag } from 'tdesign-react';
import type { ReactNode } from 'react';
import {
  AppIcon,
  ArrowLeftIcon,
  CheckCircleIcon,
  CloudUploadIcon,
  CodeIcon,
} from 'tdesign-icons-react';

import type { useSkillMarketplaceController } from '../controller/useSkillMarketplaceController';
import type { MarketplaceView } from '../model';
import { SkillCatalogView } from './SkillCatalogView';
import { SkillImportView } from './SkillImportView';
import { SkillReferenceView } from './SkillReferenceView';

export type SkillMarketplaceController = ReturnType<typeof useSkillMarketplaceController>;

export function SkillsMarketplaceShell({
  controller,
}: {
  controller: SkillMarketplaceController;
}) {
  const {
    accountIdentity,
    accountPlan,
    closing,
    closeMarketplace,
    setView,
    t,
    view,
  } = controller;
  const nav: Array<{
    id: MarketplaceView;
    label: string;
    icon: ReactNode;
  }> = [
    { id: 'catalog', label: t('allSkills'), icon: <AppIcon /> },
    { id: 'installed', label: t('installedSkills'), icon: <CheckCircleIcon /> },
    { id: 'docs', label: t('componentApiDocs'), icon: <CodeIcon /> },
    { id: 'upload', label: t('myPrivateSkills'), icon: <CloudUploadIcon /> },
  ];

  return (
    <div className={`skills-page ${closing ? 'is-closing' : ''}`} role="dialog" aria-modal="true" aria-label={t('skillsMarketplace')}>
      <header className="skills-page-header">
        <Button
          className="skills-page-back"
          shape="circle"
          variant="text"
          icon={<ArrowLeftIcon />}
          aria-label={t('backToMain')}
          title={t('backToMain')}
          onClick={(event) => {
            event.stopPropagation();
            closeMarketplace();
          }}
        />
        <div className="skills-page-brand">
          <span className="skills-page-logo" aria-hidden="true">{t('skillLogoGlyph')}</span>
          <div><strong>{t('skillsMarketplace')}</strong><small>{t('standardSkillsSubtitle')}</small></div>
        </div>
        <div className="skills-page-account">
          <Tag theme="primary" variant="light">
            {accountPlan || t('guestPlan')}
          </Tag>
          {accountIdentity?.avatar_url
            ? <img src={accountIdentity.avatar_url} alt="" referrerPolicy="no-referrer" />
            : <span className="skills-page-account-avatar" aria-hidden="true">
              {(accountIdentity?.display_name || t('guestUser')).slice(0, 1)}
            </span>}
          <span>{accountIdentity?.display_name || t('guestUser')}</span>
          {(!accountIdentity || accountIdentity.auth_type === 'guest') && (
            <Button size="small" theme="primary" onClick={controller.login}>
              {controller.loginLabel}
            </Button>
          )}
        </div>
      </header>

      <div className="skills-page-layout">
        <aside className="skills-page-nav" aria-label={t('skillsMarketplace')}>
          {nav.map((item) => (
            <button
              type="button"
              key={item.id}
              className={view === item.id ? 'is-active' : ''}
              onClick={() => setView(item.id)}
            ><span aria-hidden="true">{item.icon}</span>{item.label}</button>
          ))}
        </aside>

        <main className="skills-page-main" aria-busy={controller.loading}>
          <div className="skills-page-view" key={view}>
            {(view === 'catalog' || view === 'installed') && (
              <SkillCatalogView controller={controller} />
            )}
            {view === 'docs' && (
              <SkillReferenceView controller={controller} />
            )}
            {view === 'upload' && <SkillImportView controller={controller} />}
          </div>
        </main>
      </div>
    </div>
  );
}
