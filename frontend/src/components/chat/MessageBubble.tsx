import { useAppDispatch, useAppState } from '../../store/appState';
import type { ChatMessage } from '../../types';
import MarkdownRenderer from '../common/MarkdownRenderer';

interface Props {
  message: ChatMessage;
}

/** One Makers chat message with trusted search metadata and follow-up chips. */
export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';
  const dispatch = useAppDispatch();
  const { messages } = useAppState();
  const isLastAIMessage = !isUser && messages[messages.length - 1]?.id === message.id;
  const searchStatus = typeof message.skill?.data?.statusText === 'string'
    ? message.skill.data.statusText
    : '正在搜索';

  return (
    <div className={`msg-row ${isUser ? 'user' : 'ai'}`}>
      <div className={`msg-avatar ${isUser ? 'user' : 'ai'}`}>{isUser ? '我' : 'AI'}</div>
      <div className="msg-content-wrap">
        <div className={`msg-bubble ${isUser ? 'user' : 'ai'}`}>
          {isUser ? message.content : (
            <>
              {message.streaming && !message.content && (
                <div className="search-progress">
                  <div className="image-generating-spinner" />
                  <span>{searchStatus}</span>
                  <span className="image-generating-dots"><span>.</span><span>.</span><span>.</span></span>
                </div>
              )}
              {message.searchResults && message.searchResults.total > 0 && (
                <div className="search-sources-bar">
                  <details>
                    <summary className="search-sources-label">
                      已搜索 {message.searchResults.total} 个来源
                      <span className="search-sources-types">
                        {Array.from(new Set(message.searchResults.results.map((result) => result.source))).map((source) => {
                          const labels: Record<string, string> = {
                            wechat: '公众号', zhihu: '知乎', baike: '百科', web: '网页', wsa: '联网',
                          };
                          return <span key={source} className="search-source-type">{labels[source] || source}</span>;
                        })}
                      </span>
                    </summary>
                    <div className="search-sources-list">
                      {message.searchResults.results.map((result, index) => {
                        const labels: Record<string, string> = {
                          wechat: '公众号', zhihu: '知乎', baike: '百科', web: '网页', wsa: '联网',
                        };
                        const title = result.title || result.url || '';
                        return (
                          <a
                            key={index}
                            href={result.url}
                            target="_blank"
                            rel="noreferrer"
                            className="search-source-chip"
                          >
                            <span className="search-source-type">{labels[result.source] || '网页'}</span>
                            <span className="search-source-title">{title.length > 30 ? `${title.slice(0, 30)}…` : title}</span>
                          </a>
                        );
                      })}
                    </div>
                  </details>
                </div>
              )}
              {message.content && <MarkdownRenderer content={message.content} searchMeta={message.searchResults} />}
              {message.streaming && message.content && <span className="typing-cursor">▊</span>}
            </>
          )}
        </div>

        {isLastAIMessage && message.followUps && message.followUps.length > 0 && (
          <div className="followup-section">
            <div className="followup-label">猜你想继续问</div>
            <div className="followup-list">
              {message.followUps.map((question, index) => (
                <button
                  key={index}
                  className="followup-chip"
                  onClick={() => dispatch({ type: 'SET_DRAFT', payload: question })}
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
