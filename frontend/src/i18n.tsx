/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

export type Language = 'zh-CN' | 'zh-TW' | 'en' | 'cat-cute' | 'cat-cold';
export const LANGUAGE_KEY = 'floris-language';

const languageLabels: Record<Language, string> = {
  'zh-CN': '简体中文', 'zh-TW': '繁體中文', en: 'English',
  'cat-cute': '可爱喵喵语', 'cat-cold': '冷酷喵喵语',
};

const dictionaries: Record<Language, Record<string, string>> = {
  'zh-CN': {
    settings: '设置', settingsTitle: 'Floris 设置', language: '界面语言',
    proactive: '主动式服务', proactiveHint: '在页面打开、日程或路线发生变化时重新检查；有重要事项时在顶部循环提醒，不打断当前对话。',
    proactiveEnabled: '启用主动服务', quietHours: '22:00–08:00 免打扰', checkNow: '立即检查',
    readingLibrary: '阅读库整理', autoOrganize: '自动整理', manualOrganize: '手动整理',
    save: '保存', cancel: '取消', send: '发送', upload: '上传文件', webSearch: '联网搜索',
    copy: '复制', saveImage: '保存为图片', confirm: '确认', close: '关闭', remove: '移除',
    askContinue: '已填入输入框，点击发送继续', saved: '已保存', translate: '翻译',
    noSaved: '暂无保存记录', translationHistory: '翻译记录',
  },
  'zh-TW': {
    settings: '設定', settingsTitle: 'Floris 設定', language: '介面語言',
    proactive: '主動式服務', proactiveHint: '開啟頁面、日程或路線變更時重新檢查；重要事項會在頂部循環提醒，不打斷目前對話。',
    proactiveEnabled: '啟用主動服務', quietHours: '22:00–08:00 勿擾', checkNow: '立即檢查',
    readingLibrary: '閱讀庫整理', autoOrganize: '自動整理', manualOrganize: '手動整理',
    save: '儲存', cancel: '取消', send: '傳送', upload: '上傳檔案', webSearch: '網路搜尋',
    copy: '複製', saveImage: '儲存為圖片', confirm: '確認', close: '關閉', remove: '移除',
    askContinue: '已填入輸入框，點擊傳送繼續', saved: '已儲存', translate: '翻譯',
    noSaved: '暫無儲存記錄', translationHistory: '翻譯記錄',
  },
  en: {
    settings: 'Settings', settingsTitle: 'Floris settings', language: 'Interface language',
    proactive: 'Proactive service', proactiveHint: 'Recheck when the page, schedule, or route changes. Important items cycle at the top without interrupting the conversation.',
    proactiveEnabled: 'Enable proactive service', quietHours: 'Quiet hours 22:00–08:00', checkNow: 'Check now',
    readingLibrary: 'Reading library', autoOrganize: 'Automatic filing', manualOrganize: 'Manual filing',
    save: 'Save', cancel: 'Cancel', send: 'Send', upload: 'Upload file', webSearch: 'Web search',
    copy: 'Copy', saveImage: 'Save as image', confirm: 'Confirm', close: 'Close', remove: 'Remove',
    askContinue: 'Filled in the input box. Send to continue', saved: 'Saved', translate: 'Translate',
    noSaved: 'No saved records', translationHistory: 'Translation history',
  },
  'cat-cute': {
    settings: '喵喵设置', settingsTitle: 'Floris 的暖爪设置', language: '喵喵语言',
    proactive: '主动喵服务', proactiveHint: '页面、日程或路线变动时会轻轻检查，有重要事情就在顶部摇尾巴提醒你喵。',
    proactiveEnabled: '打开主动喵', quietHours: '22:00–08:00 安静喵', checkNow: '现在检查喵',
    readingLibrary: '阅读小窝', autoOrganize: '自动整理喵', manualOrganize: '手动整理喵',
    save: '保存喵', cancel: '先不要喵', send: '发送喵', upload: '上传文件喵', webSearch: '联网搜索喵',
    copy: '复制喵', saveImage: '保存图片喵', confirm: '确认喵', close: '关掉喵', remove: '移走喵',
    askContinue: '已经填好啦，点发送继续喵', saved: '保存好啦喵', translate: '翻译喵',
    noSaved: '还没有保存记录喵', translationHistory: '翻译小爪印',
  },
  'cat-cold': {
    settings: '设置', settingsTitle: 'Floris 设置', language: '输出语言',
    proactive: '主动服务', proactiveHint: '状态变化会自动检查。重要事项只在顶部提示，不打扰对话。',
    proactiveEnabled: '启用主动服务', quietHours: '22:00–08:00 静默', checkNow: '立即检查',
    readingLibrary: '阅读库', autoOrganize: '自动整理', manualOrganize: '手动整理',
    save: '保存', cancel: '取消', send: '发送', upload: '上传文件', webSearch: '联网搜索',
    copy: '复制', saveImage: '保存图片', confirm: '确认', close: '关闭', remove: '移除',
    askContinue: '信息已填入。发送，继续。', saved: '已保存', translate: '翻译',
    noSaved: '无保存记录', translationHistory: '翻译记录',
  },
};

export function getStoredLanguage(): Language {
  try {
    const value = localStorage.getItem(LANGUAGE_KEY) as Language | null;
    if (value && value in languageLabels) return value;
  } catch { /* private mode */ }
  return 'zh-CN';
}

export function languageInstruction(language: Language): string {
  if (language === 'en') return 'Respond in clear, natural English unless the user explicitly requests another language.';
  if (language === 'zh-TW') return '請使用自然、清晰的繁體中文回答；保留 Markdown 結構與連結。';
  if (language === 'cat-cute') return '请使用简体中文回答，语气像一只亲人的可爱橘猫，适度加入“喵”，但保持信息准确、清晰，不要过度卖萌。';
  if (language === 'cat-cold') return '请使用简体中文回答，语气像一只冷静、克制的橘猫，偶尔使用简短的“喵”，不要撒娇，保持信息准确、直接。';
  return '请使用自然、清晰的简体中文回答；保留 Markdown 结构与链接。';
}

export function languageName(language: Language): string {
  return languageLabels[language];
}

interface LanguageContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string) => string;
  modelInstruction: string;
}
const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(() => getStoredLanguage());
  const setLanguage = (next: Language) => {
    setLanguageState(next);
    try { localStorage.setItem(LANGUAGE_KEY, next); } catch { /* ignore */ }
  };
  const value = useMemo(() => ({
    language, setLanguage,
    t: (key: string) => dictionaries[language][key] || dictionaries['zh-CN'][key] || key,
    modelInstruction: languageInstruction(language),
  }), [language]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const value = useContext(LanguageContext);
  if (!value) throw new Error('useLanguage must be used inside LanguageProvider');
  return value;
}
