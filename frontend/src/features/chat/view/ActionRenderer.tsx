import type { ChatMessage } from '../model';


export function ActionRenderer({ message }: { message: ChatMessage }) {
  if (!message.workspaceActions?.length) return null;
  return (
    <div className="workspace-action-summary" data-action-count={message.workspaceActions.length}>
      {message.workspaceActions.map((action) => action.kind).join(' · ')}
    </div>
  );
}
