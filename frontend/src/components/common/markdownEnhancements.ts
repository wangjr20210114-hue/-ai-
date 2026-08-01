import { useEffect, useState } from 'react';


export interface MarkdownEnhancements {
  hljs: typeof import('highlight.js/lib/common').default;
  remarkMath: typeof import('remark-math').default;
  rehypeKatex: typeof import('rehype-katex').default;
}

let enhancementsCache: MarkdownEnhancements | null = null;
let enhancementsPromise: Promise<MarkdownEnhancements> | null = null;

export function loadMarkdownEnhancements(): Promise<MarkdownEnhancements> {
  if (!enhancementsPromise) {
    enhancementsPromise = Promise.all([
      import('highlight.js/lib/common'),
      import('remark-math'),
      import('rehype-katex'),
      import('katex/dist/katex.min.css'),
    ]).then(([hljsModule, remarkMathModule, rehypeKatexModule]) => {
      enhancementsCache = {
        hljs: hljsModule.default,
        remarkMath: remarkMathModule.default,
        rehypeKatex: rehypeKatexModule.default,
      };
      return enhancementsCache;
    });
  }
  return enhancementsPromise;
}

export function useMarkdownEnhancements(): MarkdownEnhancements | null {
  const [enhancements, setEnhancements] = useState<MarkdownEnhancements | null>(
    () => enhancementsCache,
  );
  useEffect(() => {
    if (enhancements) return;
    let alive = true;
    void loadMarkdownEnhancements().then((loaded) => {
      if (alive) setEnhancements(loaded);
    });
    return () => {
      alive = false;
    };
  }, [enhancements]);
  return enhancements;
}
