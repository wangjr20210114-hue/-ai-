import type { WSClient } from '../../services/websocket';
import MessageList from './MessageList';
import InputBar from './InputBar';

interface Props {
  client: React.RefObject<WSClient | null>;
}

/** 对话主容器：消息流 + 输入栏（元宝式居中布局）。 */
export default function ChatInterface({ client }: Props) {
  return (
    <section className="main-area panel">
      <MessageList client={client} />
      <InputBar client={client} />
    </section>
  );
}
