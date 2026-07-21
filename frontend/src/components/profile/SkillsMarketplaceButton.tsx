import { useEffect, useState } from 'react';
import { Button, Dialog, MessagePlugin, Tag } from 'tdesign-react';
import { AppIcon } from 'tdesign-icons-react';
import { useAppState } from '../../store/appState';
import { skillsOperation } from '../../services/api';

interface MarketplaceSkill {
  id: string;
  name: string;
  description: string;
  configured: boolean;
  install_url?: string;
  credential_name?: string;
}

export default function SkillsMarketplaceButton() {
  const { conversationId } = useAppState();
  const [visible, setVisible] = useState(false);
  const [skills, setSkills] = useState<MarketplaceSkill[]>([]);
  const [loading, setLoading] = useState(false);
  const refresh = async () => {
    setLoading(true);
    try { setSkills((await skillsOperation(conversationId)).skills || []); }
    catch (error) { MessagePlugin.error(error instanceof Error ? error.message : '读取 Skills 状态失败'); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (visible) void refresh(); }, [visible]);
  return <>
    <Button className="sidebar-settings-button" block variant="text" icon={<AppIcon />} onClick={() => setVisible(true)}>Skills 广场</Button>
    <Dialog visible={visible} header="Skills 广场" width={680} footer={false} onClose={() => setVisible(false)} onCancel={() => setVisible(false)}>
      <div className="skills-marketplace">
        {skills.map((skill) => <article className="skill-market-card" key={skill.id}>
          <div className="skill-market-icon">会</div>
          <div className="skill-market-content">
            <div className="skill-market-title"><strong>{skill.name}</strong><Tag size="small" theme={skill.configured ? 'success' : 'default'}>{skill.configured ? '已连接' : '未安装'}</Tag></div>
            <p>{skill.description}</p>
            {!skill.configured && <ol>
              <li>点击“开始安装”，登录腾讯会议并在 AI Skill 页面获取个人 Token。</li>
              <li>把 Token 作为 Preview 环境变量 <code>{skill.credential_name || 'TENCENT_MEETING_TOKEN'}</code> 保存；Token 等同账号身份，请勿写进网页或仓库。</li>
              <li>重新部署 Preview 后回到这里点击“刷新状态”。</li>
            </ol>}
            <div className="skill-market-actions">
              {skill.install_url && <Button theme="primary" onClick={() => window.open(skill.install_url, '_blank', 'noopener,noreferrer')}>{skill.configured ? '管理授权' : '开始安装'}</Button>}
              <Button variant="outline" loading={loading} onClick={() => void refresh()}>刷新状态</Button>
            </div>
          </div>
        </article>)}
        {!skills.length && !loading && <div className="conversation-list-empty">暂无可安装 Skill</div>}
      </div>
    </Dialog>
  </>;
}
