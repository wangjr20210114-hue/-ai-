import type { ReactNode } from 'react';

import { LanguageProvider } from '../i18n';
import { AppProvider } from '../store/AppContext';


export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <LanguageProvider>
      <AppProvider>{children}</AppProvider>
    </LanguageProvider>
  );
}
