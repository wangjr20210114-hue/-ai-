import { useEffect } from 'react';
import { useSSEChat } from './hooks/useSSEChat';
import { useWebSocket } from './hooks/useWebSocket';
import { useAppState } from './store/appState';
import Header from './components/common/Header';
import ChatInterface from './components/chat/ChatInterface';
import MyPanel from './components/profile/MyPanel';
import DebugPanel from './components/common/DebugPanel';
import EdgeOnePlatformPanel from './components/profile/EdgeOnePlatformPanel';
import { isEdgeOne } from './services/auth';
import type { ChatClient } from './services/chatClient';
import type { RefObject } from 'react';

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
        {isEdgeOne ? <EdgeOnePlatformPanel /> : <MyPanel />}
      </div>
      {!isEdgeOne && <DebugPanel />}
    </div>
  );
}

function MakersApp() {
  return <AppLayout client={useSSEChat()} />;
}

function LocalApp() {
  return <AppLayout client={useWebSocket()} />;
}

function App() {
  return isEdgeOne ? <MakersApp /> : <LocalApp />;
}

export default App;
