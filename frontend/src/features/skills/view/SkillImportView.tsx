import { useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Button, Tag } from 'tdesign-react';
import {
  CloudUploadIcon,
  DeleteIcon,
  FileMarkdownIcon,
  FilePasteIcon,
  FolderOpenIcon,
  FolderZipIcon,
  GitRepositoryIcon,
  SendIcon,
} from 'tdesign-icons-react';

import type { SkillMarketplaceController } from './SkillsMarketplaceShell';

type ImportMethod = 'file' | 'folder' | 'paste' | 'url' | 'archive';

export function SkillImportView({
  controller,
}: {
  controller: SkillMarketplaceController;
}) {
  const {
    importFile, importFolder, importText, importUrl, language, login, loginLabel,
    marketplace, publishArchive, publishUserSkill, removeUserSkill, savingId, setUserSkillEnabled,
    t, uploadArchive, uploads, userSkills,
  } = controller;
  const [method, setMethod] = useState<ImportMethod>('file');
  const [pasted, setPasted] = useState('');
  const [repositoryUrl, setRepositoryUrl] = useState('');
  const fileRef = useRef<HTMLInputElement | null>(null);
  const folderRef = useRef<HTMLInputElement | null>(null);
  const archiveRef = controller.uploadRef;
  const methods: Array<{ id: ImportMethod; label: string; hint: string; icon: ReactNode }> = [
    { id: 'file', label: t('skillImportFile'), hint: t('skillImportFileHint'), icon: <FileMarkdownIcon /> },
    { id: 'folder', label: t('skillImportFolder'), hint: t('skillImportFolderHint'), icon: <FolderOpenIcon /> },
    { id: 'paste', label: t('skillImportPaste'), hint: t('skillImportPasteHint'), icon: <FilePasteIcon /> },
    { id: 'url', label: t('skillImportRepository'), hint: t('skillImportRepositoryHint'), icon: <GitRepositoryIcon /> },
    { id: 'archive', label: t('skillPrivateArchive'), hint: t('skillPrivateArchiveHint'), icon: <FolderZipIcon /> },
  ];

  return (
    <section className="skills-page-section skills-import-page">
      <span className="skills-page-eyebrow">{t('userSkillsEyebrow')}</span>
      <h1>{t('myPrivateSkills')}</h1>
      <p>{t('privateSkillsHint')}</p>
      {!marketplace || marketplace.identity.auth_type === 'guest' ? (
        <div className="skills-login-gate">
          <strong>{t('loginRequiredForSkills')}</strong>
          <p>{t('loginSkillReason')}</p>
          <Button theme="primary" onClick={login}>{loginLabel}</Button>
        </div>
      ) : <>
        <div className="skill-import-methods" role="tablist" aria-label={t('skillImportMethods')}>
          {methods.map((item, index) => <button
            type="button"
            role="tab"
            aria-selected={method === item.id}
            key={item.id}
            className={method === item.id ? 'is-active' : ''}
            style={{ '--skill-index': index } as CSSProperties}
            onClick={() => setMethod(item.id)}
          >
            <span aria-hidden="true">{item.icon}</span>
            <strong>{item.label}</strong>
            <small>{item.hint}</small>
          </button>)}
        </div>

        <div className="skill-import-workbench">
          {method === 'file' && <div className="skill-import-action">
            <FileMarkdownIcon aria-hidden="true" />
            <div><strong>{t('skillSelectDeclarativeFile')}</strong><small>{t('skillDeclarativeSafety')}</small></div>
            <input
              ref={fileRef}
              type="file"
              accept=".md,.json,text/markdown,application/json"
              onChange={async (event) => {
                if (await importFile(event.target.files?.[0])) event.target.value = '';
              }}
            />
            <Button theme="primary" loading={savingId === 'private-skill'} onClick={() => fileRef.current?.click()}>
              {t('chooseFile')}
            </Button>
          </div>}

          {method === 'folder' && <div className="skill-import-action">
            <FolderOpenIcon aria-hidden="true" />
            <div><strong>{t('skillSelectFolder')}</strong><small>{t('skillFolderSafety')}</small></div>
            <input
              ref={(element) => {
                folderRef.current = element;
                element?.setAttribute('webkitdirectory', '');
              }}
              type="file"
              multiple
              onChange={async (event) => {
                if (await importFolder(event.target.files)) event.target.value = '';
              }}
            />
            <Button theme="primary" loading={savingId === 'private-skill'} onClick={() => folderRef.current?.click()}>
              {t('chooseFolder')}
            </Button>
          </div>}

          {method === 'paste' && <div className="skill-import-editor">
            <label htmlFor="private-skill-markdown">{t('skillPasteLabel')}</label>
            <textarea
              id="private-skill-markdown"
              value={pasted}
              maxLength={12_000}
              placeholder={t('skillPastePlaceholder')}
              onChange={(event) => setPasted(event.target.value)}
            />
            <div><small>{t('skillCharacterCount', { count: pasted.length.toLocaleString(language) })}</small><Button
              theme="primary"
              icon={<CloudUploadIcon />}
              disabled={!pasted.trim()}
              loading={savingId === 'private-skill'}
              onClick={async () => {
                if (await importText(pasted)) setPasted('');
              }}
            >{t('installPrivately')}</Button></div>
          </div>}

          {method === 'url' && <div className="skill-import-editor is-url">
            <label htmlFor="private-skill-url">{t('skillRepositoryUrl')}</label>
            <div className="skill-url-row">
              <input
                id="private-skill-url"
                type="url"
                value={repositoryUrl}
                placeholder={t('skillRepositoryPlaceholder')}
                onChange={(event) => setRepositoryUrl(event.target.value)}
              />
              <Button
                theme="primary"
                icon={<CloudUploadIcon />}
                disabled={!repositoryUrl.trim()}
                loading={savingId === 'private-skill'}
                onClick={async () => {
                  if (await importUrl(repositoryUrl)) setRepositoryUrl('');
                }}
              >{t('importSkill')}</Button>
            </div>
            <small>{t('skillRepositorySecurity')}</small>
          </div>}

          {method === 'archive' && <div className="skill-import-action">
            <FolderZipIcon aria-hidden="true" />
            <div><strong>{t('selectSkillZip')}</strong><small>{t('skillPrivateArchiveSafety')}</small></div>
            <input
              ref={archiveRef}
              type="file"
              accept=".zip,application/zip,application/x-zip-compressed"
              onChange={(event) => void uploadArchive(event.target.files?.[0])}
            />
            <Button theme="primary" loading={savingId === 'archive'} onClick={() => archiveRef.current?.click()}>
              {t('chooseFile')}
            </Button>
          </div>}
        </div>

        <div className="private-skill-library">
          <div className="private-skill-library-title">
            <div><strong>{t('privateSkillLibrary')}</strong><small>{t('privateSkillLibraryHint')}</small></div>
            <Tag variant="light">{userSkills.length + uploads.filter((item) => item.source_type !== 'declarative').length}</Tag>
          </div>
          <div className="private-skill-list">
            {userSkills.map((item, index) => {
              const review = uploads.find((upload) => upload.source_skill_id === item.id);
              return <article
                key={item.id}
                style={{ '--skill-index': index } as CSSProperties}
              >
                <span className="private-skill-icon" aria-hidden="true"><FileMarkdownIcon /></span>
                <div>
                  <strong>{item.name}</strong>
                  <small>{item.description || t('declarativePrivateSkill')} · {t('privateOnly')}</small>
                </div>
                <Tag theme={item.enabled ? 'success' : 'default'} variant="light">
                  {t(item.enabled ? 'enabled' : 'disabled')}
                </Tag>
                <Button
                  size="small"
                  variant="outline"
                  loading={savingId === item.id}
                  onClick={() => void setUserSkillEnabled(item.id, !item.enabled)}
                >{t(item.enabled ? 'disableAction' : 'enableAction')}</Button>
                <Button
                  size="small"
                  theme="primary"
                  variant="outline"
                  icon={<SendIcon />}
                  disabled={review?.review_status === 'pending_review'}
                  loading={savingId === item.id}
                  onClick={() => void publishUserSkill(item)}
                >{review?.review_status === 'pending_review' ? t('pendingReview') : t('publishToMarketplace')}</Button>
                <Button
                  shape="circle"
                  size="small"
                  variant="text"
                  icon={<DeleteIcon />}
                  aria-label={t('removePrivateSkill')}
                  title={t('removePrivateSkill')}
                  onClick={() => {
                    if (window.confirm(t('removePrivateSkillConfirm', { name: item.name }))) {
                      void removeUserSkill(item.id);
                    }
                  }}
                />
              </article>;
            })}
            {uploads.filter((item) => item.source_type !== 'declarative').map((item, index) => <article
              key={item.id}
              style={{ '--skill-index': index + userSkills.length } as CSSProperties}
            >
              <span className="private-skill-icon is-archive" aria-hidden="true"><FolderZipIcon /></span>
              <div>
                <strong>{item.name}</strong>
                <small>{t('privateArchiveStored')} · {t('privateOnly')}</small>
              </div>
              {item.review_status === 'pending_review'
                ? <Tag theme="warning">{t('pendingReview')}</Tag>
                : <Tag>{t('notSubmittedForReview')}</Tag>}
              <Button
                size="small"
                theme="primary"
                variant="outline"
                icon={<SendIcon />}
                disabled={item.review_status === 'pending_review'}
                loading={savingId === item.id}
                onClick={() => void publishArchive(item.id)}
              >{t('publishToMarketplace')}</Button>
            </article>)}
            {!userSkills.length && !uploads.length && <div className="private-skill-empty">
              <CloudUploadIcon aria-hidden="true" />
              <strong>{t('noPrivateSkills')}</strong>
              <small>{t('noPrivateSkillsHint')}</small>
            </div>}
          </div>
        </div>
      </>}
    </section>
  );
}
