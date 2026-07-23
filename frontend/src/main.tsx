import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'tdesign-react/es/style/index.css'
import './index.css'
import App from './App.tsx'
import { AppProvider } from './store/AppContext.tsx'
import { LanguageProvider } from './i18n.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LanguageProvider><AppProvider><App /></AppProvider></LanguageProvider>
  </StrictMode>,
)
