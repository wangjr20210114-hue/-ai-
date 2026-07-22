export interface SkillCatalogEntry {
  id: string;
  name: string;
  icon: string;
  description: string;
  locked?: boolean;
  requires?: string[];
  recommends?: string[];
  external?: boolean;
}

export const SKILLS_CATALOG: SkillCatalogEntry[] = [
  { id: 'core', name: '通用问答与创作', icon: '✦', description: '问答、写作、翻译、总结与自然对话。核心能力始终开启。', locked: true },
  { id: 'web-search', name: '实时搜索', icon: '⌕', description: '检索时效信息、核验来源并为回答提供真实图片素材。' },
  { id: 'vision', name: '视觉理解', icon: '◉', description: '理解用户上传的图片，并审核搜索图片是否与问题真正相关。' },
  { id: 'image-studio', name: '图片工坊', icon: '◇', description: '混元文生图、参考图生图和连续修改。', recommends: ['vision', 'web-search'] },
  { id: 'maps', name: '真实地点与地图', icon: '⌖', description: '核实餐馆、景点和地址，并在地图中显示真实坐标。' },
  { id: 'calendar', name: '日程管理', icon: '▦', description: '通过对话或日历新增、修改、删除日程并检查冲突。', recommends: ['maps'] },
  { id: 'proactive-agent', name: '主动式 Agent', icon: '✧', description: '根据日程、天气、路线与工作流主动发现机会并提醒。', recommends: ['calendar', 'maps'] },
  { id: 'paper-reading', name: '论文检索与助读', icon: '▤', description: '查找论文、下载 PDF 并在页面内进行结构化助读。', recommends: ['web-search'] },
  { id: 'tencent-meeting', name: '腾讯会议', icon: '会', description: '创建真实腾讯会议，并将会议号和链接同步写入日程。', requires: ['calendar'], external: true },
];

export const SKILL_NAME = Object.fromEntries(SKILLS_CATALOG.map((skill) => [skill.id, skill.name]));
