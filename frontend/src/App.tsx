import { useEffect } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { useAppState } from './store/appState';
import Header from './components/common/Header';
import ChatInterface from './components/chat/ChatInterface';
import MyPanel from './components/profile/MyPanel';

function App() {
  const client = useWebSocket();
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
    </div>
  );
}

export default App;
