import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'tdesign-react/es/style/index.css'
import './styles/index.css'
import App from './app/App.tsx'
import { AppProviders } from './app/AppProviders.tsx'
import { restoreCloudBaseSession } from './features/auth/model/cloudbaseClient.ts'
import { consumeOAuthLoginIntent } from './features/auth/model/loginIntent.ts'
import { ensureAuthSession } from './shared/auth/session.ts'

function renderApp() {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <AppProviders><App /></AppProviders>
    </StrictMode>,
  )
}

renderApp()

// Establish the browser session without delaying first paint. A provider
// session is exchanged automatically only while completing an OAuth redirect;
// ordinary logout and natural cookie expiry remain visibly signed out.
void ensureAuthSession()
  .then((session) => (
    session.identity.auth_type === 'guest' && consumeOAuthLoginIntent()
      ? restoreCloudBaseSession()
      : session
  ))
  .catch(() => null)
