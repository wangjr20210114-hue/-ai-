import { useState } from 'react';
import { Button, Collapse } from 'tdesign-react';
import { ChevronUpIcon, ChevronDownIcon } from 'tdesign-icons-react';
import AgentActivityCenter from '../profile/AgentActivityCenter';
import AgentIntelligencePanel from '../profile/AgentIntelligencePanel';
import SystemSafetyPanel from '../profile/SystemSafetyPanel';

export default function DebugPanel() {
  const [open, setOpen] = useState(false);

  return (
    <div style={{ borderTop: '1px solid var(--app-border)', background: 'var(--app-bg)', flexShrink: 0 }}>
      <div
        style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', padding: '6px 12px' }}
        onClick={() => setOpen(!open)}
      >
        <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--app-text-3)', flex: 1 }}>
          Debug
        </span>
        <Button size="small" variant="text" icon={open ? <ChevronDownIcon /> : <ChevronUpIcon />} />
      </div>
      {open && (
        <div style={{ padding: '0 12px 12px', maxHeight: 400, overflowY: 'auto' }}>
          <Collapse defaultExpandAll>
            <Collapse.Panel header="Agent Activity Center" value="activity">
              <AgentActivityCenter />
            </Collapse.Panel>
            <Collapse.Panel header="记忆与预算" value="memory">
              <AgentIntelligencePanel />
            </Collapse.Panel>
            <Collapse.Panel header="系统安全与恢复" value="system">
              <SystemSafetyPanel />
            </Collapse.Panel>
          </Collapse>
        </div>
      )}
    </div>
  );
}
