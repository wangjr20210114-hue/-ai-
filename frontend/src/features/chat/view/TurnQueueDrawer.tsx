import { useEffect, useState, type RefObject } from 'react';
import { Button, Input } from 'tdesign-react';
import {
  ChevronDownIcon,
  ChevronUpIcon,
  DeleteIcon,
  EditIcon,
  JumpIcon,
} from 'tdesign-icons-react';
import type { ChatClient } from '../../../services/chatClient';
import type { ChatQueueItem } from '../model';
import { useLanguage } from '../../../i18n';

interface Props {
  client: RefObject<ChatClient | null>;
  items: ChatQueueItem[];
}

export default function TurnQueueDrawer({ client, items }: Props) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(true);
  const [editingId, setEditingId] = useState('');
  const [editingContent, setEditingContent] = useState('');
  const [interruptingId, setInterruptingId] = useState('');

  useEffect(() => {
    if (items.length) setOpen(true);
    if (editingId && !items.some((item) => item.id === editingId)) {
      setEditingId('');
      setEditingContent('');
    }
  }, [editingId, items]);

  if (!items.length) return null;

  const saveEdit = () => {
    if (client.current?.updateQueuedTurn?.(editingId, editingContent)) {
      setEditingId('');
      setEditingContent('');
    }
  };

  const interrupt = async (id: string) => {
    if (!client.current?.interruptWithQueuedTurn || interruptingId) return;
    setInterruptingId(id);
    try {
      await client.current.interruptWithQueuedTurn(id);
    } finally {
      setInterruptingId('');
    }
  };

  return (
    <section className={`turn-queue-drawer${open ? ' is-open' : ''}`} aria-label={t('turnQueue')}>
      <button
        type="button"
        className="turn-queue-toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span>{t('turnQueueCount', { count: items.length })}</span>
        {open ? <ChevronDownIcon /> : <ChevronUpIcon />}
      </button>
      <div className="turn-queue-content" aria-hidden={!open}>
        <div className="turn-queue-list">
          {items.map((item, index) => (
            <div className="turn-queue-item" key={item.id}>
              <span className="turn-queue-order">{index + 1}</span>
              {editingId === item.id ? (
                <Input
                  className="turn-queue-editor"
                  value={editingContent}
                  autofocus
                  onChange={(value) => setEditingContent(String(value))}
                  onEnter={saveEdit}
                  onBlur={saveEdit}
                  aria-label={t('editQueuedTurn')}
                />
              ) : (
                <span className="turn-queue-text" title={item.content}>{item.content}</span>
              )}
              <div className="turn-queue-actions">
                <Button
                  variant="text"
                  shape="circle"
                  size="small"
                  icon={<EditIcon />}
                  onClick={() => {
                    setEditingId(item.id);
                    setEditingContent(item.content);
                  }}
                  aria-label={t('editQueuedTurn')}
                  title={t('editQueuedTurn')}
                />
                <Button
                  variant="text"
                  shape="circle"
                  size="small"
                  icon={<DeleteIcon />}
                  onClick={() => client.current?.removeQueuedTurn?.(item.id)}
                  aria-label={t('removeQueuedTurn')}
                  title={t('removeQueuedTurn')}
                />
                <Button
                  variant="text"
                  shape="circle"
                  size="small"
                  icon={<JumpIcon />}
                  loading={interruptingId === item.id}
                  disabled={Boolean(interruptingId)}
                  onClick={() => { void interrupt(item.id); }}
                  aria-label={t('interruptWithQueuedTurn')}
                  title={t('interruptWithQueuedTurn')}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
