import { Button, Tag } from 'tdesign-react';
import type { ReactNode } from 'react';
import {
  AppIcon,
  ArrowLeftIcon,
  CheckCircleIcon,
  CloudUploadIcon,
  CodeIcon,
  TreeRoundDotIcon,
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
  const { closeMarketplace, marketplace, setView, t, view } = controller;
  const nav: Array<{
    id: MarketplaceView;
    label: string;
    icon: ReactNode;
  }> = [
    { id: 'catalog', label: t('allSkills'), icon: <AppIcon /> },
    { id: 'installed', label: t('installedSkills'), icon: <CheckCircleIcon /> },
    { id: 'dependencies', label: t('dependencyGraph'), icon: <TreeRoundDotIcon /> },
    { id: 'docs', label: t('componentApiDocs'), icon: <CodeIcon /> },
    { id: 'upload', label: t('myPrivateSkills'), icon: <CloudUploadIcon /> },
  ];

  return (
    <div className="skills-page" role="dialog" aria-modal="true" aria-label={t('skillsMarketplace')}>
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
            {marketplace?.entitlements.plan || t('guestPlan')}
          </Tag>
          {marketplace?.identity.avatar_url
            ? <img src={marketplace.identity.avatar_url} alt="" referrerPolicy="no-referrer" />
            : <span className="skills-page-account-avatar" aria-hidden="true">
              {(marketplace?.identity.display_name || t('guestUser')).slice(0, 1)}
            </span>}
          <span>{marketplace?.identity.display_name || t('guestUser')}</span>
          {(!marketplace || marketplace.identity.auth_type === 'guest') && (
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
          <div className="skills-page-nav-note">
            <strong>{t('makersNative')}</strong>
            <span>{t('makersNativeSkillNote')}</span>
          </div>
        </aside>

        <main className="skills-page-main" aria-busy={controller.loading}>
          <div className="skills-page-view" key={view}>
            {(view === 'catalog' || view === 'installed') && (
              <SkillCatalogView controller={controller} />
            )}
            {(view === 'dependencies' || view === 'docs') && (
              <SkillReferenceView controller={controller} />
            )}
            {view === 'upload' && <SkillImportView controller={controller} />}
          </div>
        </main>
      </div>
    </div>
  );
}
