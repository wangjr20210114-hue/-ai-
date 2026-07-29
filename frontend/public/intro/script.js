/* FLORIS 介绍站交互：主题、滚动揭示、自动播放的对话演示 */
(() => {
  'use strict';

  const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const SITE_URL = '/chat/';

  /* ================= 主题 ================= */
  const root = document.documentElement;
  const THEME_KEY = 'floris-intro-theme';
  const wipe = document.getElementById('theme-wipe');
  const themeCtaLabel = () => document.querySelector('.theme-cta-label');

  function currentTheme() {
    return root.getAttribute('theme-mode') === 'dark' ? 'dark' : 'light';
  }

  function applyTheme(mode) {
    root.setAttribute('theme-mode', mode);
    const label = themeCtaLabel();
    if (label) label.textContent = mode === 'dark' ? '切换到清晨' : '切换到夜空';
    try { localStorage.setItem(THEME_KEY, mode); } catch { /* optional */ }
  }

  function initialTheme() {
    try {
      const saved = localStorage.getItem(THEME_KEY);
      if (saved === 'dark' || saved === 'light') return saved;
    } catch { /* optional */ }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  applyTheme(initialTheme());

  function toggleTheme(x, y) {
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    if (REDUCED || !wipe) { applyTheme(next); return; }
    const radius = Math.hypot(
      Math.max(x, window.innerWidth - x),
      Math.max(y, window.innerHeight - y),
    );
    wipe.style.background = next === 'dark'
      ? 'radial-gradient(circle at 14% 5%, rgba(139,92,246,.2), transparent 38%), #100c1d'
      : 'radial-gradient(circle at 14% 5%, rgba(242,139,66,.16), transparent 38%), #fff8f0';
    wipe.style.transition = 'none';
    wipe.style.clipPath = `circle(0px at ${x}px ${y}px)`;
    wipe.classList.add('is-running');
    // 强制 reflow 后再展开
    void wipe.offsetWidth;
    wipe.style.transition = '';
    wipe.style.clipPath = `circle(${radius}px at ${x}px ${y}px)`;
    window.setTimeout(() => {
      applyTheme(next);
      wipe.style.transition = 'opacity 240ms ease';
      wipe.style.opacity = '0';
      window.setTimeout(() => {
        wipe.classList.remove('is-running');
        wipe.style.cssText = '';
      }, 260);
    }, 500);
  }

  document.getElementById('theme-toggle').addEventListener('click', (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    toggleTheme(rect.left + rect.width / 2, rect.top + rect.height / 2);
  });
  document.getElementById('theme-cta').addEventListener('click', (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    toggleTheme(rect.left + rect.width / 2, rect.top + rect.height / 2);
  });

  /* ================= 滚动揭示 ================= */
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        revealObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });
  document.querySelectorAll('.reveal').forEach((el) => revealObserver.observe(el));

  /* ================= 能力网格 ================= */
  const FEATURES = [
    { icon: '🔎', title: '富文本加强搜索', desc: '最直白、最靠谱、最实时的方式回复你，让回答的含金量直线提升。', query: '最近 AI 有啥新消息？' },
    { icon: '🗺️', title: '路程规划 & 地点搜索', desc: '晚上去哪吃、周末去哪玩，帮你准确回答并标注在地图上。', query: '我附近有啥玩的？' },
    { icon: '📅', title: '日程规划', desc: '自动为你制定日程，在合适的时机提醒，还能一句话更改。', query: '我明天就想去这些地方玩！' },
    { icon: '📄', title: '论文 & 文档助读', desc: '帮你收集文献，助读器可总结、可翻译，科研狗的得力助手。', query: '给我找两篇 XX 方向的论文' },
    { icon: '🃏', title: '主动式 Card', desc: '知之为知之，不知为不知。它会先发几张卡片问清楚，再给你最靠谱的答案。' },
    { icon: '🎨', title: '图片工坊', desc: '它还是个大画家，可以画出你脑海的星空，还能给相似图片做对比。', query: '请帮我画一个你' },
    { icon: '🧩', title: 'Skill 分离设计', desc: '所有能力封装成独立 Skill，热插拔，想探索的程序猿可以方便地扩展它。' },
    { icon: '💗', title: '贴心细节', desc: '从你的行程习惯推测所需并主动分享，文献自动整理成文件夹，日夜双主题护眼。' },
  ];
  const grid = document.getElementById('features-grid');
  grid.innerHTML = FEATURES.map((f, i) => `
    <article class="feature-card reveal" style="--reveal-delay: ${i * 60}ms">
      <span class="feature-icon" aria-hidden="true">${f.icon}</span>
      <h3>${f.title}</h3>
      <p>${f.desc}</p>
      ${f.query ? `<span class="feature-query">“${f.query}”</span>` : ''}
    </article>
  `).join('');
  grid.querySelectorAll('.reveal').forEach((el) => revealObserver.observe(el));

  /* ================= 对话演示 ================= */
  const chat = document.getElementById('demo-chat');
  const tabsBar = document.getElementById('demo-tabs');
  const liveBadge = document.getElementById('demo-live');

  const AVATAR = '/intro/assets/floris-avatar.png';

  const cards = {
    sources: () => `
      <div class="demo-card">
        <div class="card-title"><span class="card-mark">◆</span>参考来源</div>
        <div class="source-pill"><span class="src-host">arxiv.org</span><span class="src-title">多模态模型新基准发布，长视频理解成焦点</span></div>
        <div class="source-pill"><span class="src-host">量子位</span><span class="src-title">Agent 工具链年度盘点：从玩具到生产力</span></div>
        <div class="source-pill"><span class="src-host">机器之心</span><span class="src-title">端侧小模型一周两连发，手机也能跑</span></div>
      </div>`,
    map: () => `
      <div class="demo-card">
        <div class="card-title"><span class="card-mark">◆</span>已在地图上标好 3 个地点</div>
        <div class="demo-map">
          <svg viewBox="0 0 320 148" role="img" aria-label="地图示意">
            <rect width="320" height="148" rx="10" style="fill:color-mix(in srgb, var(--brand) 7%, var(--app-panel))"/>
            <path d="M-8 46 C 60 30, 130 66, 200 44 S 320 58, 340 40" fill="none" style="stroke:var(--app-border-strong)" stroke-width="5" stroke-linecap="round" opacity=".6"/>
            <path d="M40 -8 C 60 40, 30 100, 58 160" fill="none" style="stroke:var(--app-border-strong)" stroke-width="4" stroke-linecap="round" opacity=".45"/>
            <path d="M150 -8 C 170 50, 150 96, 176 160" fill="none" style="stroke:var(--app-border-strong)" stroke-width="4" stroke-linecap="round" opacity=".45"/>
            <path class="map-route" d="M84 108 C 120 84, 150 74, 168 66 S 226 44, 246 38" fill="none" style="stroke:var(--brand)" stroke-width="2.6" stroke-linecap="round" stroke-dasharray="6 7"/>
            <g class="map-pin" transform="translate(84 108)"><path d="M0 0 C -8 -9 -8 -22 0 -22 C 8 -22 8 -9 0 0" style="fill:var(--brand)"/><circle cy="-15" r="2.6" fill="#fff"/></g>
            <g class="map-pin" transform="translate(168 66)"><path d="M0 0 C -8 -9 -8 -22 0 -22 C 8 -22 8 -9 0 0" style="fill:var(--brand)"/><circle cy="-15" r="2.6" fill="#fff"/></g>
            <g class="map-pin" transform="translate(246 38)"><path d="M0 0 C -8 -9 -8 -22 0 -22 C 8 -22 8 -9 0 0" style="fill:var(--brand)"/><circle cy="-15" r="2.6" fill="#fff"/></g>
          </svg>
        </div>
        <button class="map-open-btn" type="button">查看地点 ›</button>
      </div>`,
    schedule: () => `
      <div class="demo-card">
        <div class="card-title"><span class="card-mark">◆</span>明天的日程，到点我会提醒你</div>
        <div class="schedule-row"><span class="schedule-time">09:30</span><span class="schedule-name">南门涮肉（取号排队）</span><span class="schedule-tag">吃</span></div>
        <div class="schedule-row"><span class="schedule-time">13:00</span><span class="schedule-name">故宫 · 中轴线半日</span><span class="schedule-tag">逛</span></div>
        <div class="schedule-row"><span class="schedule-time">19:00</span><span class="schedule-name">后海散步 + 糖葫芦</span><span class="schedule-tag">遛弯</span></div>
      </div>`,
    papers: () => `
      <div class="demo-card">
        <div class="card-title"><span class="card-mark">◆</span>为你找到 2 篇论文</div>
        <div class="paper-item">
          <span class="paper-source">arXiv · 2026</span>
          <strong class="paper-name">OmniVL: Unified Multi-modal Understanding at Scale</strong>
          <span class="paper-authors">Y. Chen, L. Wang, K. Zhou 等</span>
          <button class="paper-read-btn" type="button">开始论文助读</button>
        </div>
        <div class="paper-item">
          <span class="paper-source">arXiv · 2025</span>
          <strong class="paper-name">Grounding Language Models in Video Streams</strong>
          <span class="paper-authors">M. Liu, J. Park, R. Gupta 等</span>
          <button class="paper-read-btn" type="button">开始论文助读</button>
        </div>
      </div>`,
    painting: () => `
      <div class="demo-card">
        <div class="card-title"><span class="card-mark">◆</span>画好啦，这就是我</div>
        <div class="painting-frame">
          <svg viewBox="0 0 300 190" role="img" aria-label="大橘自画像">
            <rect width="300" height="190" fill="url(#sky)"/>
            <defs>
              <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stop-color="#2b2350"/><stop offset="1" stop-color="#120e24"/>
              </linearGradient>
              <radialGradient id="glow" cx="0.5" cy="0.42" r="0.55">
                <stop offset="0" stop-color="#ffd9a0" stop-opacity=".32"/><stop offset="1" stop-color="#ffd9a0" stop-opacity="0"/>
              </radialGradient>
            </defs>
            <circle cx="52" cy="34" r="1.4" fill="#fff" opacity=".8"/><circle cx="248" cy="26" r="1.2" fill="#fff" opacity=".7"/>
            <circle cx="206" cy="52" r="1.6" fill="#fff" opacity=".85"/><circle cx="96" cy="20" r="1.1" fill="#fff" opacity=".6"/>
            <circle cx="270" cy="86" r="1.3" fill="#fff" opacity=".65"/><circle cx="30" cy="88" r="1.2" fill="#fff" opacity=".55"/>
            <rect width="300" height="190" fill="url(#glow)"/>
            <g>
              <path d="M106 66 L96 30 L132 48 Z" fill="#e8853b"/>
              <path d="M194 66 L204 30 L168 48 Z" fill="#e8853b"/>
              <path d="M110 60 L103 39 L124 50 Z" fill="#f9c896"/>
              <path d="M190 60 L197 39 L176 50 Z" fill="#f9c896"/>
              <ellipse cx="150" cy="112" rx="58" ry="52" fill="#f2a54a"/>
              <ellipse cx="150" cy="130" rx="34" ry="26" fill="#f9d3a3"/>
              <path d="M124 104 q 8 7 16 0" fill="none" stroke="#5a3416" stroke-width="3.4" stroke-linecap="round"/>
              <path d="M160 104 q 8 7 16 0" fill="none" stroke="#5a3416" stroke-width="3.4" stroke-linecap="round"/>
              <path d="M146 118 h8 l -4 6 z" fill="#d4703a"/>
              <path d="M150 124 q -4 7 -12 6 M150 124 q 4 7 12 6" fill="none" stroke="#5a3416" stroke-width="2.6" stroke-linecap="round"/>
              <path d="M96 116 h-22 M98 124 l-20 5 M204 116 h22 M202 124 l20 5" stroke="#caa06e" stroke-width="2.2" stroke-linecap="round"/>
              <ellipse cx="116" cy="122" rx="7" ry="4.4" fill="#f0885a" opacity=".55"/>
              <ellipse cx="184" cy="122" rx="7" ry="4.4" fill="#f0885a" opacity=".55"/>
              <path d="M132 84 q 18 -10 36 0" fill="none" stroke="#d4703a" stroke-width="3" stroke-linecap="round" opacity=".6"/>
            </g>
          </svg>
          <span class="painting-sweep"></span>
        </div>
        <p class="painting-caption">AI 生成插画 · 还可以继续说「让表情变得凶狠！」做对比</p>
      </div>`,
    clarify: () => `
      <div class="demo-card">
        <div class="card-title"><span class="card-mark">◆</span>出发前，先和你确认两件事</div>
        <div class="clarify-field">
          <span class="clarify-label">从哪里出发？</span>
          <div class="clarify-options">
            <button class="clarify-chip" data-pick type="button">就用我的当前位置</button>
            <button class="clarify-chip" type="button">手动填一个</button>
          </div>
        </div>
        <div class="clarify-field">
          <span class="clarify-label">怎么去？</span>
          <div class="clarify-options">
            <button class="clarify-chip" data-pick type="button">高铁</button>
            <button class="clarify-chip" type="button">飞机</button>
            <button class="clarify-chip" type="button">自驾</button>
          </div>
        </div>
        <button class="clarify-submit" type="button">填好了，继续思考 ›</button>
      </div>`,
  };

  const SCENES = [
    { id: 'search', tab: '富搜索', user: '最近 AI 有啥新消息？',
      ai: '帮你看了下今天的进展：多模态模型继续卷，Agent 应用开始落到日常工具里。我挑了 3 条最值得看的，来源都标好啦～', card: 'sources' },
    { id: 'map', tab: '周边地点', user: '我附近有啥玩的？',
      ai: '你附近 3 公里内，这 3 个地方评价最好，已经帮你在地图上标出来了～', card: 'map' },
    { id: 'schedule', tab: '日程规划', user: '我明天就想去这些地方玩！',
      ai: '安排！按距离顺路排好了，到点我会提醒你。你只管考虑玩，剩下的交给我。', card: 'schedule' },
    { id: 'papers', tab: '论文助读', user: '帮我找两篇多模态方向的论文',
      ai: '找到 2 篇最对口的，点开就能用助读器，总结翻译都可以，早点看完早点睡。', card: 'papers' },
    { id: 'painting', tab: '图片工坊', user: '请帮我画一个你',
      ai: '好呀，酝酿了一下……这就是我眼里的自己，喜欢吗？', card: 'painting' },
    { id: 'clarify', tab: '主动提问', user: '帮我安排明天去北京的行程',
      ai: '这个我得先问清楚，免得给你瞎安排。填一下小卡片，我马上继续想：', card: 'clarify' },
  ];

  let generation = 0;
  let playing = true;
  let sceneIndex = 0;

  const wait = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

  async function waitWhilePaused(gen) {
    while (!playing && gen === generation) await wait(240);
  }

  function sceneDuration(scene) {
    return 500 + 900 + scene.ai.length * 30 + (scene.card ? 1500 : 0) + 2800;
  }

  function buildTabs() {
    tabsBar.innerHTML = SCENES.map((scene, i) => `
      <button class="demo-tab" role="tab" aria-selected="false" data-index="${i}" type="button">
        ${scene.tab}<span class="tab-progress"></span>
      </button>
    `).join('');
    tabsBar.querySelectorAll('.demo-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        sceneIndex = Number(tab.dataset.index);
        generation += 1;
        playing = true;
        updateLiveBadge();
        void playLoop();
      });
    });
  }

  function activateTab(index, scene) {
    tabsBar.querySelectorAll('.demo-tab').forEach((tab, i) => {
      const active = i === index;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', String(active));
      if (active) {
        const progress = tab.querySelector('.tab-progress');
        progress.style.animation = 'none';
        void progress.offsetWidth;
        progress.style.animation = '';
        tab.style.setProperty('--scene-duration', `${sceneDuration(scene)}ms`);
      }
    });
  }

  function updateLiveBadge() {
    liveBadge.classList.toggle('is-paused', !playing);
    liveBadge.innerHTML = `<i></i>${playing ? '播放中' : '已暂停'}`;
  }

  function scrollChat() {
    chat.scrollTo({ top: chat.scrollHeight, behavior: REDUCED ? 'auto' : 'smooth' });
  }

  function addUserRow(text) {
    const row = document.createElement('div');
    row.className = 'msg-row user';
    row.innerHTML = `<div class="msg-bubble"></div>`;
    row.firstElementChild.textContent = text;
    chat.appendChild(row);
    scrollChat();
    return row;
  }

  function addAiRow() {
    const row = document.createElement('div');
    row.className = 'msg-row ai';
    row.innerHTML = `
      <span class="msg-avatar"><img src="${AVATAR}" alt=""></span>
      <div class="msg-bubble"><span class="typing-dots"><span></span><span></span><span></span></span></div>
    `;
    chat.appendChild(row);
    scrollChat();
    return row;
  }

  async function streamText(bubble, text, gen) {
    bubble.innerHTML = '<span class="stream-text"></span><span class="stream-cursor"></span>';
    const target = bubble.querySelector('.stream-text');
    for (let i = 0; i < text.length; i += 1) {
      if (gen !== generation) return false;
      await waitWhilePaused(gen);
      target.textContent += text[i];
      if (i % 3 === 0) scrollChat();
      await wait(30);
    }
    await wait(280);
    bubble.querySelector('.stream-cursor')?.remove();
    scrollChat();
    return gen === generation;
  }

  async function revealCard(bubble, scene, gen) {
    const skeleton = document.createElement('div');
    skeleton.className = 'card-skeleton';
    skeleton.innerHTML = '<span class="skeleton" style="width:42%"></span><span class="skeleton"></span><span class="skeleton" style="width:76%"></span>';
    bubble.appendChild(skeleton);
    scrollChat();
    await wait(820);
    if (gen !== generation) return false;
    skeleton.remove();
    const wrapper = document.createElement('div');
    wrapper.innerHTML = cards[scene.card]();
    const card = wrapper.firstElementChild;
    bubble.appendChild(card);
    scrollChat();
    if (scene.card === 'clarify') {
      await wait(750);
      if (gen !== generation) return false;
      card.querySelectorAll('[data-pick]').forEach((chip) => chip.classList.add('is-picked'));
      await wait(480);
      if (gen !== generation) return false;
      card.querySelector('.clarify-submit')?.classList.add('is-ready');
    }
    return gen === generation;
  }

  async function playScene(index) {
    const gen = generation;
    const scene = SCENES[index];
    activateTab(index, scene);
    chat.innerHTML = '';
    await wait(420);
    if (gen !== generation) return;
    addUserRow(scene.user);
    await wait(650);
    if (gen !== generation) return;
    await waitWhilePaused(gen);
    const row = addAiRow();
    await wait(1000);
    if (gen !== generation) return;
    const bubble = row.querySelector('.msg-bubble');
    if (!await streamText(bubble, scene.ai, gen)) return;
    if (scene.card && !await revealCard(bubble, scene, gen)) return;
    await wait(2800);
  }

  async function playLoop() {
    const gen = generation;
    while (gen === generation) {
      await waitWhilePaused(gen);
      if (gen !== generation) return;
      await playScene(sceneIndex);
      if (gen !== generation) return;
      sceneIndex = (sceneIndex + 1) % SCENES.length;
    }
  }

  // 减动效：不自动播放，直接呈现第一个完整场景
  async function renderStaticScene(index) {
    const gen = generation;
    const scene = SCENES[index];
    activateTab(index, scene);
    chat.innerHTML = '';
    addUserRow(scene.user);
    const row = addAiRow();
    const bubble = row.querySelector('.msg-bubble');
    bubble.textContent = scene.ai;
    if (scene.card) {
      const wrapper = document.createElement('div');
      wrapper.innerHTML = cards[scene.card]();
      bubble.appendChild(wrapper.firstElementChild);
      if (scene.card === 'clarify') {
        bubble.querySelectorAll('[data-pick]').forEach((chip) => chip.classList.add('is-picked'));
        bubble.querySelector('.clarify-submit')?.classList.add('is-ready');
      }
    }
    if (gen !== generation) return;
  }

  buildTabs();

  if (REDUCED) {
    playing = false;
    updateLiveBadge();
    liveBadge.innerHTML = '<i></i>减动效模式';
    void renderStaticScene(0);
    tabsBar.querySelectorAll('.demo-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        generation += 1;
        void renderStaticScene(Number(tab.dataset.index));
      }, { once: false });
    });
  } else {
    updateLiveBadge();
    void playLoop();
    // 滚出视口暂停播放
    new IntersectionObserver((entries) => {
      playing = entries[0].isIntersecting;
      updateLiveBadge();
    }, { threshold: 0.22 }).observe(chat);
  }

  // 演示窗口内的模拟按钮：点了就真的去主站
  chat.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest('.map-open-btn') || target.closest('.paper-read-btn') || target.closest('.demo-send') || target.closest('.clarify-submit')) {
      window.open(SITE_URL, '_blank', 'noopener');
    }
  });
  document.querySelector('.demo-inputbar')?.addEventListener('click', (event) => {
    if (event.target instanceof Element && event.target.closest('.demo-send')) {
      window.open(SITE_URL, '_blank', 'noopener');
    }
  });
})();
