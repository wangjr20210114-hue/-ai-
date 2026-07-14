import type { ChatClient } from '../../services/chatClient';
import MessageList from './MessageList';
import InputBar from './InputBar';

interface Props {
  client: React.RefObject<ChatClient | null>;
}

/** 对话主容器：消息流 + 输入栏（元宝式居中布局）。 */
export default function ChatInterface({ client }: Props) {
  return (
    <section className="main-area panel">
      <MessageList />
      <InputBar client={client} />
    </section>
  );
}
