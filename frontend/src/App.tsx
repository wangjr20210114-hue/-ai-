import { useEffect } from 'react';
import { useSSEChat } from './hooks/useSSEChat';
import { useAppState } from './store/appState';
import Header from './components/common/Header';
import ChatInterface from './components/chat/ChatInterface';
import MyPanel from './components/profile/MyPanel';
import DebugPanel from './components/common/DebugPanel';

function App() {
  const client = useSSEChat();
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
      <DebugPanel />
    </div>
  );
}

export default App;
