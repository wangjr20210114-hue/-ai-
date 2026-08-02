import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'tdesign-react/es/style/index.css'
import './styles/index.css'
import App from './app/App.tsx'
import { AppProviders } from './app/AppProviders.tsx'
import { ensureAuthSession } from './shared/auth/session.ts'

function renderApp() {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <AppProviders><App /></AppProviders>
    </StrictMode>,
  )
}

renderApp()

// Establish the browser session without automatically reviving a provider
// account after an explicit logout. Account continuation is always explicit.
void ensureAuthSession().catch(() => null)
