/**
 * InfoCard — 统一信息卡片组件。
 * 用于搜索结果、公众号推荐、论文推荐、地点推荐等场景。
 *
 * 结构：
 * ┌──────────────────────────────────────────────┐
 * │ [图标]  标题                          [来源] │
 * │         摘要（一行）                          │
 * │         标签1  标签2              [操作按钮]  │
 * └──────────────────────────────────────────────┘
 */
import React from 'react';
import { useLanguage, type TranslationKey } from '../../i18n';

export type CardType = 'wechat' | 'zhihu' | 'baike' | 'web' | 'paper' | 'location' | 'video' | 'music' | 'book' | 'movie';

export interface CardTag {
  label: string;
  color?: string;
}

export interface InfoCardProps {
  /** 卡片类型，决定图标和配色 */
  type: CardType | string;
  /** 标题 */
  title: string;
  /** 链接（点击跳转），可选 */
  url?: string;
  /** 摘要（一行，超出省略） */
  snippet?: string;
  /** 头像/图片 URL，可选（左侧显示） */
  image?: string;
  /** 右上角来源标签文字（如"公众号""知乎""arXiv"） */
  sourceLabel?: string;
  /** 标签列表 */
  tags?: CardTag[];
  /** 右侧操作按钮文字（如"下载""阅读"），可选 */
  actionLabel?: string;
  /** 操作按钮点击回调 */
  onAction?: () => void;
  /** 操作按钮 loading 状态 */
  actionLoading?: boolean;
  /** 右侧附加内容（如自定义按钮组） */
  extra?: React.ReactNode;
  /** 是否紧凑模式（更小内边距） */
  compact?: boolean;
  /** 点击卡片回调（不传则不响应点击） */
  onClick?: () => void;
}

const TYPE_CONFIG: Record<string, { icon: string; color: string; bg: string; defaultLabelKey: TranslationKey }> = {
  wechat:   { icon: '微', color: '#07c160', bg: 'rgba(7,193,96,0.06)', defaultLabelKey: 'sourceWechat' },
  zhihu:    { icon: '知', color: '#0066ff', bg: 'rgba(0,102,255,0.06)', defaultLabelKey: 'sourceZhihu' },
  baike:    { icon: '📖', color: '#e37318', bg: 'rgba(227,115,24,0.06)', defaultLabelKey: 'sourceEncyclopedia' },
  web:      { icon: '🔗', color: '#5a6072', bg: 'rgba(90,96,114,0.06)', defaultLabelKey: 'sourceWeb' },
  paper:    { icon: '📄', color: '#7c5cff', bg: 'rgba(124,92,255,0.06)', defaultLabelKey: 'sourcePaper' },
  location: { icon: '📍', color: '#2b5aed', bg: 'rgba(43,90,237,0.06)', defaultLabelKey: 'sourceLocation' },
  video:    { icon: '🎬', color: '#ff6b6b', bg: 'rgba(255,107,107,0.06)', defaultLabelKey: 'sourceVideo' },
  music:    { icon: '🎵', color: '#1db954', bg: 'rgba(29,185,84,0.06)', defaultLabelKey: 'sourceMusic' },
  book:     { icon: '📚', color: '#e37318', bg: 'rgba(227,115,24,0.06)', defaultLabelKey: 'sourceBook' },
  movie:    { icon: '🎭', color: '#ff6b6b', bg: 'rgba(255,107,107,0.06)', defaultLabelKey: 'sourceMovie' },
};

export default function InfoCard({
  type,
  title,
  url,
  snippet,
  image,
  sourceLabel,
  tags,
  actionLabel,
  onAction,
  actionLoading,
  extra,
  compact,
  onClick,
}: InfoCardProps) {
  const { t } = useLanguage();
  const cfg = TYPE_CONFIG[type] || TYPE_CONFIG.web;
  const label = sourceLabel || t(cfg.defaultLabelKey);
  const pad = compact ? '6px 10px' : '10px 12px';

  const inner = (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: pad,
        borderRadius: 10,
        border: `1px solid ${cfg.color}1a`,
        background: cfg.bg,
        transition: 'all 0.15s',
        cursor: onClick || url ? 'pointer' : 'default',
      }}
      onMouseEnter={(e) => {
        if (onClick || url) e.currentTarget.style.borderColor = cfg.color + '44';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = cfg.color + '1a';
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget || !(e.target as HTMLElement).closest('button,a')) {
          onClick?.();
        }
      }}
    >
      {/* 左侧图标/头像 */}
      {image ? (
        <img
          src={image}
          alt={title}
          style={{
            width: 36, height: 36, borderRadius: 8,
            flexShrink: 0, objectFit: 'cover',
          }}
          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
        />
      ) : (
        <div style={{
          width: 32, height: 32, borderRadius: 7,
          flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: cfg.color, color: '#fff',
          fontSize: type === 'wechat' || type === 'zhihu' ? 11 : 14,
          fontWeight: 600,
        }}>
          {cfg.icon}
        </div>
      )}

      {/* 中间内容 */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 13, fontWeight: 500,
          color: 'var(--app-text, #1d2129)',
          overflow: 'hidden', textOverflow: 'ellipsis',
          whiteSpace: 'nowrap', lineHeight: 1.3,
        }}>
          {title}
        </div>
        {snippet && (
          <div style={{
            fontSize: 11.5, color: 'var(--app-text-3, #939aad)',
            marginTop: 1, lineHeight: 1.4,
            overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {snippet}
          </div>
        )}
        {tags && tags.length > 0 && (
          <div style={{ display: 'flex', gap: 4, marginTop: 3, flexWrap: 'wrap' }}>
            {tags.map((t, i) => (
              <span key={i} style={{
                fontSize: 10, fontWeight: 500,
                color: t.color || 'var(--app-text-3, #939aad)',
                background: 'var(--app-bg, #f4f6fb)',
                padding: '1px 6px', borderRadius: 4,
              }}>
                {t.label}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* 右侧：来源标签 + 操作按钮 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
        {extra}
        {actionLabel && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onAction?.();
            }}
            disabled={actionLoading}
            style={{
              fontSize: 11, fontWeight: 500,
              color: '#fff', background: cfg.color,
              border: 'none', borderRadius: 6,
              padding: '4px 10px', cursor: 'pointer',
              opacity: actionLoading ? 0.6 : 1,
            }}
          >
            {actionLoading ? '...' : actionLabel}
          </button>
        )}
        <span style={{
          fontSize: 10, fontWeight: 600,
          color: cfg.color, background: cfg.bg,
          padding: '2px 7px', borderRadius: 4,
          border: `1px solid ${cfg.color}22`,
        }}>
          {label}
        </span>
      </div>
    </div>
  );

  // 如果有 url 且没有自定义 onClick，用 a 标签包裹
  if (url && !onClick) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        style={{ textDecoration: 'none', color: 'inherit', display: 'block', margin: `${compact ? 4 : 8}px 0` }}
      >
        {inner}
      </a>
    );
  }

  return <div style={{ margin: `${compact ? 4 : 8}px 0` }}>{inner}</div>;
}
