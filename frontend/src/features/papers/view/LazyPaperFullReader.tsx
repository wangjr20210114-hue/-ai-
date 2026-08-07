import { lazy, Suspense } from 'react';
import { Button, Loading } from 'tdesign-react';
import { CloseIcon } from 'tdesign-icons-react';

import { useLanguage } from '../../../i18n';
import type { PaperFullReaderProps } from './PaperFullReader';

const PaperFullReader = lazy(() => import('./PaperFullReader'));

export default function LazyPaperFullReader(props: PaperFullReaderProps) {
  const { t } = useLanguage();
  return (
    <Suspense fallback={(
      <div className="paper-reader-lazy-loading" role="status" aria-label={t('loading')}>
        <div className="paper-reader-lazy-status">
          <Loading size="small" />
          <span>{t('openingCompatiblePreview')}</span>
        </div>
        <Button
          shape="circle"
          variant="text"
          icon={<CloseIcon />}
          aria-label={t('closePaperAssistant')}
          title={t('closePaperAssistant')}
          onClick={props.onClose}
        />
      </div>
    )}>
      <PaperFullReader {...props} />
    </Suspense>
  );
}
