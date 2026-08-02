import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import { createPortal } from 'react-dom';
import { ChevronRightIcon } from 'tdesign-icons-react';
import { useLanguage, type TranslationKey } from '../../i18n';
import {
  completeOnboarding,
  disableOnboarding,
  OPEN_ONBOARDING_EVENT,
  shouldOpenOnboarding,
} from '../../services/onboarding';
import { FEATURE_DOCUMENT_URL } from '../../constants';

type TourMode = 'hidden' | 'welcome' | 'tour' | 'settings-hint';
type TourArea = 'sidebar' | 'workspace' | 'header';

interface TourStep {
  key: string;
  copy: TranslationKey;
  area: TourArea;
  selectors: string[];
}

interface TargetRect {
  top: number;
  left: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

interface Props {
  connected: boolean;
  revealArea: (area: TourArea) => void;
}

const STEPS: TourStep[] = [
  {
    key: 'new-conversation',
    copy: 'onboardingNewConversation',
    area: 'sidebar',
    selectors: ['[data-onboarding="new-conversation"]'],
  },
  {
    key: 'conversation-history',
    copy: 'onboardingHistory',
    area: 'sidebar',
    selectors: ['[data-onboarding="conversation-history"]'],
  },
  {
    key: 'map',
    copy: 'onboardingMap',
    area: 'workspace',
    selectors: ['[data-onboarding="map"]'],
  },
  {
    key: 'calendar',
    copy: 'onboardingCalendar',
    area: 'workspace',
    selectors: ['[data-onboarding="calendar"]'],
  },
  {
    key: 'reading',
    copy: 'onboardingReading',
    area: 'workspace',
    selectors: ['[data-onboarding="reading"]'],
  },
  {
    key: 'proactive',
    copy: 'onboardingReminders',
    area: 'sidebar',
    selectors: ['[data-onboarding="reminders"]', '[data-onboarding="header-reminder"]'],
  },
  {
    key: 'skills',
    copy: 'onboardingSkills',
    area: 'sidebar',
    selectors: ['[data-onboarding="skills"]'],
  },
  {
    key: 'settings',
    copy: 'onboardingSettings',
    area: 'sidebar',
    selectors: ['[data-onboarding="settings"]'],
  },
  {
    key: 'theme',
    copy: 'onboardingTheme',
    area: 'header',
    selectors: ['[data-onboarding="theme"]'],
  },
  {
    key: 'github',
    copy: 'onboardingGithub',
    area: 'header',
    selectors: ['[data-onboarding="github"]'],
  },
];

function visibleRect(element: Element): TargetRect | null {
  const style = window.getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  if (
    style.display === 'none'
    || style.visibility === 'hidden'
    || rect.width < 2
    || rect.height < 2
    || rect.bottom <= 0
    || rect.top >= window.innerHeight
  ) return null;
  return {
    top: Math.max(0, rect.top),
    left: Math.max(0, rect.left),
    right: Math.min(window.innerWidth, rect.right),
    bottom: Math.min(window.innerHeight, rect.bottom),
    width: Math.min(window.innerWidth, rect.right) - Math.max(0, rect.left),
    height: Math.min(window.innerHeight, rect.bottom) - Math.max(0, rect.top),
  };
}

function boundsFor(rects: TargetRect[]): TargetRect | null {
  if (!rects.length) return null;
  const top = Math.min(...rects.map((rect) => rect.top));
  const left = Math.min(...rects.map((rect) => rect.left));
  const right = Math.max(...rects.map((rect) => rect.right));
  const bottom = Math.max(...rects.map((rect) => rect.bottom));
  return { top, left, right, bottom, width: right - left, height: bottom - top };
}

function blurTilesFor(rects: TargetRect[], gutter = 8): CSSProperties[] {
  if (!rects.length) return [];
  const holes = rects.map((rect) => ({
    top: Math.max(0, rect.top - gutter),
    left: Math.max(0, rect.left - gutter),
    right: Math.min(window.innerWidth, rect.right + gutter),
    bottom: Math.min(window.innerHeight, rect.bottom + gutter),
  }));
  const xs = [...new Set([0, window.innerWidth, ...holes.flatMap((hole) => [hole.left, hole.right])])]
    .sort((first, second) => first - second);
  const ys = [...new Set([0, window.innerHeight, ...holes.flatMap((hole) => [hole.top, hole.bottom])])]
    .sort((first, second) => first - second);
  const tiles: CSSProperties[] = [];
  for (let x = 0; x < xs.length - 1; x += 1) {
    for (let y = 0; y < ys.length - 1; y += 1) {
      const left = xs[x];
      const right = xs[x + 1];
      const top = ys[y];
      const bottom = ys[y + 1];
      const centerX = (left + right) / 2;
      const centerY = (top + bottom) / 2;
      if (holes.some((hole) => (
        centerX >= hole.left && centerX <= hole.right
        && centerY >= hole.top && centerY <= hole.bottom
      ))) continue;
      if (right > left && bottom > top) {
        tiles.push({ left, top, width: right - left, height: bottom - top });
      }
    }
  }
  return tiles;
}

function popoverStyle(anchor: TargetRect | null, estimatedHeight = 220): CSSProperties {
  const margin = 16;
  const width = Math.min(372, window.innerWidth - margin * 2);
  if (!anchor) {
    return {
      width,
      left: Math.max(margin, (window.innerWidth - width) / 2),
      top: '50%',
      transform: 'translateY(-50%)',
    };
  }

  let top = anchor.bottom + 18;
  if (top + estimatedHeight > window.innerHeight - margin) {
    top = anchor.top - estimatedHeight - 18;
  }
  if (top < margin) {
    top = Math.min(
      window.innerHeight - estimatedHeight - margin,
      Math.max(margin, anchor.top + anchor.height / 2 - estimatedHeight / 2),
    );
  }
  const centered = anchor.left + anchor.width / 2 - width / 2;
  return {
    width,
    left: Math.min(window.innerWidth - width - margin, Math.max(margin, centered)),
    top,
  };
}

export default function FlorisOnboarding({ connected, revealArea }: Props) {
  const { t } = useLanguage();
  const [mode, setMode] = useState<TourMode>('hidden');
  const [stepIndex, setStepIndex] = useState(0);
  const [rects, setRects] = useState<TargetRect[]>([]);
  const openedAutomatically = useRef(false);
  const portalId = useId().replace(/:/g, '');

  const step = STEPS[stepIndex];
  const selectors = mode === 'settings-hint'
    ? ['.header-account']
    : mode === 'tour'
      ? step.selectors
      : [];
  const bounds = useMemo(() => boundsFor(rects), [rects]);
  const blurTiles = useMemo(() => blurTilesFor(rects), [rects]);
  const anchor = rects[0] || bounds;

  const refreshRects = useCallback(() => {
    const next = selectors.flatMap((selector) => {
      const element = document.querySelector(selector);
      const rect = element ? visibleRect(element) : null;
      return rect ? [rect] : [];
    });
    setRects(next);
  }, [selectors.join('|')]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!connected || openedAutomatically.current || !shouldOpenOnboarding()) return;
    openedAutomatically.current = true;
    const timer = window.setTimeout(() => setMode('welcome'), 240);
    return () => window.clearTimeout(timer);
  }, [connected]);

  useEffect(() => {
    const open = (event: Event) => {
      const detail = (event as CustomEvent<{ startImmediately?: boolean }>).detail;
      setStepIndex(0);
      setMode(detail?.startImmediately ? 'tour' : 'welcome');
    };
    window.addEventListener(OPEN_ONBOARDING_EVENT, open);
    return () => window.removeEventListener(OPEN_ONBOARDING_EVENT, open);
  }, []);

  useEffect(() => {
    if (mode === 'tour') revealArea(step.area);
    if (mode === 'settings-hint') revealArea('sidebar');
  }, [mode, revealArea, step?.area]);

  useEffect(() => {
    if (mode === 'hidden' || mode === 'welcome') {
      setRects([]);
      return;
    }

    let frame = 0;
    let settleTimer = 0;
    const update = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(refreshRects);
    };
    update();
    settleTimer = window.setTimeout(() => {
      const first = document.querySelector(selectors[0]);
      first?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
      update();
    }, 260);
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(settleTimer);
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [mode, refreshRects, selectors.join('|')]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (mode === 'hidden') return;
    const app = document.querySelector<HTMLElement>('.app-shell');
    const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const nativeControls = new Set<
      HTMLButtonElement | HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
    >();
    const semanticControls = new Set<HTMLElement>();
    const lockControls = (root: ParentNode) => {
      root.querySelectorAll<
        HTMLButtonElement | HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
      >('button, input, select, textarea').forEach((control) => {
        if (control.disabled || nativeControls.has(control)) return;
        nativeControls.add(control);
        control.disabled = true;
        control.dataset.onboardingTourDisabled = 'true';
      });
      root.querySelectorAll<HTMLElement>(
        'a[href], [role="button"], [role="switch"]',
      ).forEach((control) => {
        if (
          control.matches('button, input, select, textarea')
          || semanticControls.has(control)
        ) return;
        semanticControls.add(control);
        control.dataset.onboardingPreviousTabindex = control.getAttribute('tabindex') ?? '';
        control.dataset.onboardingPreviousAriaDisabled = control.getAttribute('aria-disabled') ?? '';
        control.setAttribute('aria-disabled', 'true');
        control.setAttribute('tabindex', '-1');
      });
    };
    if (app) lockControls(app);
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => mutation.addedNodes.forEach((node) => {
        if (node instanceof HTMLElement) lockControls(node);
      }));
    });
    if (app) observer.observe(app, { childList: true, subtree: true });
    app?.setAttribute('inert', '');
    app?.classList.add('is-onboarding-locked');
    return () => {
      observer.disconnect();
      nativeControls.forEach((control) => {
        if (control.dataset.onboardingTourDisabled !== 'true') return;
        control.disabled = false;
        delete control.dataset.onboardingTourDisabled;
      });
      semanticControls.forEach((control) => {
        const previousTabindex = control.dataset.onboardingPreviousTabindex;
        const previousAriaDisabled = control.dataset.onboardingPreviousAriaDisabled;
        if (previousTabindex === '') control.removeAttribute('tabindex');
        else if (previousTabindex !== undefined) control.setAttribute('tabindex', previousTabindex);
        if (previousAriaDisabled === '') control.removeAttribute('aria-disabled');
        else if (previousAriaDisabled !== undefined) control.setAttribute('aria-disabled', previousAriaDisabled);
        delete control.dataset.onboardingPreviousTabindex;
        delete control.dataset.onboardingPreviousAriaDisabled;
      });
      app?.removeAttribute('inert');
      app?.classList.remove('is-onboarding-locked');
      active?.focus({ preventScroll: true });
    };
  }, [mode]);

  useEffect(() => {
    if (mode === 'hidden') return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      disableOnboarding();
      setMode('settings-hint');
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [mode]);

  const begin = () => {
    setStepIndex(0);
    setMode('tour');
  };

  const dismiss = () => {
    disableOnboarding();
    setMode('settings-hint');
  };

  const finish = () => {
    completeOnboarding();
    setMode('hidden');
  };

  const next = () => {
    if (stepIndex >= STEPS.length - 1) {
      finish();
      return;
    }
    setRects([]);
    setStepIndex((value) => value + 1);
  };

  if (mode === 'hidden') return null;

  const welcome = mode === 'welcome';
  const hint = mode === 'settings-hint';
  const cardStyle = welcome
    ? popoverStyle(null)
    : popoverStyle(anchor, hint ? 312 : 220);

  return createPortal(
    <div
      className={`floris-onboarding floris-onboarding-${mode}`}
      role="dialog"
      aria-modal="true"
      aria-labelledby={`floris-onboarding-title-${portalId}`}
    >
      <div className="floris-onboarding-interaction-lock" aria-hidden="true" />
      {welcome ? (
        <div className="floris-onboarding-welcome-scrim" aria-hidden="true" />
      ) : bounds ? (
        <>
          {blurTiles.map((style, index) => (
            <div className="floris-onboarding-blur" style={style} key={`blur-${index}`} />
          ))}
          {rects.map((rect, index) => (
            <div
              className="floris-onboarding-focus-ring"
              key={`${step?.key || 'hint'}-${index}`}
              style={{
                top: rect.top - 7,
                left: rect.left - 7,
                width: rect.width + 14,
                height: rect.height + 14,
              }}
            />
          ))}
        </>
      ) : (
        <div className="floris-onboarding-welcome-scrim" aria-hidden="true" />
      )}

      <section
        key={welcome ? 'welcome' : hint ? 'settings-hint' : step.key}
        className={`floris-onboarding-card${welcome ? ' is-welcome' : ''}`}
        style={cardStyle}
      >
        <div className="floris-onboarding-cat-mark" aria-hidden="true">
          <img src="/floris-avatar.png" alt="" />
          <span>{welcome ? '✦' : '⌁'}</span>
        </div>
        {welcome ? (
          <>
            <h2 id={`floris-onboarding-title-${portalId}`}>{t('onboardingWelcomeTitle')}</h2>
            <div className="floris-onboarding-welcome-copy">
              <p>{t('onboardingOwners')}</p>
              <p>
                <a href={FEATURE_DOCUMENT_URL} target="_blank" rel="noreferrer noopener">
                  {t('onboardingGithubWelcome')}
                </a>
              </p>
              <p>{t('onboardingIntroOffer')}</p>
            </div>
            <div className="floris-onboarding-welcome-actions">
              <button type="button" className="is-primary" onClick={begin}>{t('onboardingStart')}</button>
              <button type="button" onClick={dismiss}>{t('onboardingSkip')}</button>
            </div>
          </>
        ) : (
          <>
            <div className="floris-onboarding-card-head">
              <span>{hint ? t('onboardingSettingTitle') : t('onboardingProgress', {
                current: stepIndex + 1,
                total: STEPS.length,
              })}</span>
              {!hint && <i style={{ '--tour-progress': `${((stepIndex + 1) / STEPS.length) * 100}%` } as CSSProperties} />}
            </div>
            <h2 id={`floris-onboarding-title-${portalId}`}>
              {hint ? t('onboardingSettingTitle') : t(step.copy)}
            </h2>
            {hint && <p className="floris-onboarding-hint-copy">{t('onboardingSkipHint')}</p>}
            <button
              type="button"
              className="floris-onboarding-next"
              onClick={hint ? () => setMode('hidden') : next}
            >
              {hint
                ? t('onboardingGotIt')
                : stepIndex === STEPS.length - 1
                  ? t('onboardingFinish')
                  : t('onboardingNext')}
              {!hint && <ChevronRightIcon />}
            </button>
          </>
        )}
      </section>
    </div>,
    document.body,
  );
}
