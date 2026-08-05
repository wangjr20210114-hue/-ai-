import { lazy, Suspense } from 'react';
import { Loading } from 'tdesign-react';

import { useLanguage } from '../../../i18n';
import type { PaperFullReaderProps } from './PaperFullReader';

const PaperFullReader = lazy(() => import('./PaperFullReader'));

export default function LazyPaperFullReader(props: PaperFullReaderProps) {
  const { t } = useLanguage();
  return (
    <Suspense fallback={(
      <div className="paper-reader-lazy-loading" role="status" aria-label={t('loading')}>
        <Loading size="small" />
        <span>{t('openingCompatiblePreview')}</span>
      </div>
    )}>
      <PaperFullReader {...props} />
    </Suspense>
  );
}
