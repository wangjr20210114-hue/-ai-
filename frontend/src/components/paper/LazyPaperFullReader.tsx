/**
 * Lazy boundary for PaperFullReader: keeps pdfjs-dist out of the initial
 * bundle. The fallback mirrors the reader overlay so opening a paper feels
 * continuous while the chunk downloads.
 */
import { lazy, Suspense } from 'react';

const PaperFullReader = lazy(() => import('./PaperFullReader'));

interface Props {
  fileId: string;
  title: string;
  arxivId?: string;
  assistantEnabled?: boolean;
  onClose: () => void;
}

function ReaderFallback() {
  return (
    <div className="paper-reader-overlay is-expanded paper-reader-fallback" role="status" aria-busy="true">
      <div className="paper-reader-fallback-panel">
        <span className="skeleton skeleton-line" style={{ width: '32%' }} />
        <div className="skeleton paper-reader-fallback-page">
          <span className="skeleton skeleton-line" style={{ width: '48%' }} />
          <span className="skeleton skeleton-line" />
          <span className="skeleton skeleton-line" />
          <span className="skeleton skeleton-line" style={{ width: '82%' }} />
          <span className="skeleton skeleton-line" style={{ width: '64%' }} />
        </div>
      </div>
    </div>
  );
}

export default function LazyPaperFullReader(props: Props) {
  return (
    <Suspense fallback={<ReaderFallback />}>
      <PaperFullReader {...props} />
    </Suspense>
  );
}
