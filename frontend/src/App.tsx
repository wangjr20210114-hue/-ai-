import { useEffect, type RefObject } from 'react';
import Header from './components/common/Header';
import ChatInterface from './components/chat/ChatInterface';
import MyPanel from './components/profile/MyPanel';
import LocationConsent from './components/profile/LocationConsent';
import { useSSEChat } from './hooks/useSSEChat';
import type { ChatClient } from './services/chatClient';
import { useAppState } from './store/appState';

function AppLayout({ client }: { client: RefObject<ChatClient | null> }) {
  const { theme } = useAppState();

  useEffect(() => {
    document.documentElement.setAttribute('theme-mode', theme);
  }, [theme]);

  return (
    <div className="app-shell">
      <Header />
      <div className="app-body">
        <ChatInterface client={client} />
        <MyPanel />
      </div>
      <LocationConsent />
    </div>
  );
}

export default function App() {
  return <AppLayout client={useSSEChat()} />;
}
