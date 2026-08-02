import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'tdesign-react/es/style/index.css'
import './styles/index.css'
import App from './app/App.tsx'
import { AppProviders } from './app/AppProviders.tsx'
import { restoreCloudBaseSession } from './features/auth/model/cloudbaseClient.ts'
import { ensureAuthSession } from './shared/auth/session.ts'

function renderApp() {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <AppProviders><App /></AppProviders>
    </StrictMode>,
  )
}

renderApp()

// Establish the signed Guest/account cookie first so an OAuth exchange can
// preserve the existing Makers subject without delaying the first paint.
void ensureAuthSession()
  .then((session) => (
    session.identity.auth_type === 'guest'
      ? restoreCloudBaseSession()
      : session
  ))
  .catch(() => null)
