package com.floris.android.ui.prefs

/** 文案键。每条必须提供全部五种语言，避免静默回退。 */
enum class StringKey {
    // 通用
    Confirm, Cancel, Retry, Done, Close, Search, Loading, Failed,
    // 处理进度（与网页端逐字一致）
    UnderstandingRequest, ProgressPlanning, ProgressRetrieval, ProgressVerification,
    ProgressSynthesis, ProgressFinalizing, ProgressComplete, ProgressWebSearch,
    ProgressPaperSearch, ProgressPlaceSearch, ProgressRoutePlanning,
    ProgressCalendarPreparation, ProgressMeetingPreparation, ProgressImageGeneration,
    ProgressImageReview, ProgressComponentAction, ProgressSafetyNote,
    OrganizingAnswer, OrganizingVerifiedAnswer, WritingReviewing,
    SearchingForSeconds, SearchCompletedIn, SearchCompleteMeta,
    PaintingUnderstand, PaintingCompose, PaintingDetail, PaintingReveal, PaintingWait,
    // 主动提醒
    Reminders, NoReminders, RefreshReminders, HandleSuggestion, Later, Ignore,
    RemindLaterAt, ReminderOperationFailed,
    // 游客与退出
    LoginAsGuest, GuestBadge, GuestUpgradeHint, ExitConfirmToast,
    LoginOr, GuestSignInCta, GuestProfileNotice,
    // 回答操作
    CopyPlainText, CopiedToClipboard, SaveAsImage, Saving, SaveImageFailed,
    // 底部导航
    TabChat, TabSkills, TabCalendar, TabReading, TabProfile,
    // 聊天
    AppTagline, ChatIntro, ChatInputHint, ChatStop, ChatNew, ChatHistory,
    SuggestNews, SuggestBooks, SuggestPlace, SuggestCode,
    ChatSources, ChatEmptyHistoryTitle, ChatEmptyHistoryBody,
    // 新手介绍
    OnboardingWelcomeTitle, OnboardingOwners, OnboardingGithubWelcome, OnboardingIntroOffer,
    OnboardingStart, OnboardingSkip, OnboardingNewConversation, OnboardingHistory,
    OnboardingMap, OnboardingCalendar, OnboardingReading, OnboardingReminders,
    OnboardingSkills, OnboardingSettings, OnboardingTheme, OnboardingGithub,
    OnboardingChatInput, OnboardingProfileCenter,
    OnboardingNext, OnboardingFinish, OnboardingSkipHint, OnboardingGotIt,
    // Skills
    SkillsEyebrow, SkillsTitle, SkillsSubtitle, SkillsSearchHint, SkillsEnabledCount,
    SkillsAlwaysOn, SkillsGuestReady, SkillsRequires, SkillsDependencies, SkillsComponentApi,
    SkillsLoginRequired, SkillsLoginHint, SkillsGuestNotice,
    // 日程
    CalendarTitle, CalendarToday, CalendarDayEmpty, CalendarEmptyTitle, CalendarEmptyBody,
    // 阅读
    ReadingTitle, ReadingSearchHint, ReadingLibrary, ReadingEmptyTitle, ReadingEmptyBody,
    ReadingSummarize, ReadingTranslate, ReadingNoResultTitle, ReadingNoResultBody,
    // 地图
    MapTitle, MapSearchHint, MapPlaces, MapRoute, MapEmptyTitle, MapEmptyBody, MapShowOnMap,
    // 个人中心
    ProfileTitle, ProfileBriefs, ProfileWorkspace, ProfileAccount, ProfileSettings,
    ProfileAbout, ProfileSignOut, ProfileMap, ProfileReading,
    // 设置
    SettingsTitle, SettingsAppearance, SettingsTheme, SettingsThemeSystem, SettingsThemeLight,
    SettingsThemeDark, SettingsLanguage, SettingsPreferences, SettingsProactive,
    SettingsProactiveDesc, SettingsWebResults, SettingsWebResultsDesc, SettingsImageCandidates,
    SettingsImageCandidatesDesc, SettingsReplayTour, SettingsReplayTourDesc, SettingsUsage,
    SettingsDailyTokens, SettingsMonthlyTokens, SettingsData, SettingsResetData,
    SettingsResetTitle, SettingsResetBody, SettingsResetConfirm, SettingsNickname, SettingsNotSet,
    // 登录
    LoginEmail, LoginSendCode, LoginSending, LoginCode, LoginSignIn, LoginSigningIn,
    LoginBackToEmail, LoginCodeSentTo,
    // 工作区动作
    ActionAwaiting, ActionReady, ActionActive, ActionExecuting, ActionSucceeded,
    ActionFailed, ActionCancelled, ActionNeedsReview, ActionUnknown,
    ClarificationSubmit, ClarificationSubmitting,
}

private typealias Entry = Array<String>

/** 顺序：简体 / 繁體 / English / 可爱喵 / 高冷喵 */
object Strings {

    private val catalog: Map<StringKey, Entry> = buildMap {
        fun put(key: StringKey, zh: String, tw: String, en: String, cute: String, cold: String) {
            put(key, arrayOf(zh, tw, en, cute, cold))
        }

        // ---- 通用 ----
        put(StringKey.Confirm, "确认", "確認", "Confirm", "好呀", "确认")
        put(StringKey.Cancel, "取消", "取消", "Cancel", "先不要", "取消")
        put(StringKey.Retry, "重试", "重試", "Retry", "再试一次", "重试")
        put(StringKey.Done, "完成", "完成", "Done", "好啦", "完成")
        put(StringKey.Close, "关闭", "關閉", "Close", "收起来", "关闭")
        put(StringKey.Search, "搜索", "搜尋", "Search", "找找看", "搜索")
        put(StringKey.Loading, "加载中…", "載入中…", "Loading…", "正在翻找…", "加载中…")
        put(StringKey.Failed, "加载失败", "載入失敗", "Failed to load", "没找到呢", "加载失败")

        // ---- 处理进度（逐字对齐网页端 i18n）----
        put(StringKey.UnderstandingRequest, "我先看一下", "我先看一下", "Let me take a look", "我先看一下喵", "我先看一下")
        put(StringKey.ProgressPlanning, "先理清问题", "先理清問題", "Understanding the question", "先理清问题喵", "先理清问题")
        put(StringKey.ProgressRetrieval, "正在找资料", "正在找資料", "Finding information", "正在找资料喵", "正在找资料")
        put(StringKey.ProgressVerification, "核对一下结果", "核對一下結果", "Checking the results", "核对一下结果喵", "核对结果")
        put(StringKey.ProgressSynthesis, "整理成回答", "整理成回答", "Putting the answer together", "整理成回答喵", "整理回答")
        put(StringKey.ProgressFinalizing, "马上就好", "馬上就好", "Almost there", "马上就好喵", "马上完成")
        put(StringKey.ProgressComplete, "完成", "完成", "Done", "完成啦喵", "完成")
        put(StringKey.ProgressWebSearch, "正在搜资料", "正在搜資料", "Searching the web", "正在搜资料喵", "正在搜资料")
        put(StringKey.ProgressPaperSearch, "正在找论文", "正在找論文", "Finding papers", "正在找论文喵", "正在找论文")
        put(StringKey.ProgressPlaceSearch, "核实地点信息", "核實地點資訊", "Verify place information", "核实地点信息喵", "核实地点信息")
        put(StringKey.ProgressRoutePlanning, "核验道路路线", "核驗道路路線", "Verify the road route", "核验道路路线喵", "核验道路路线")
        put(
            StringKey.ProgressCalendarPreparation,
            "校验日程变更", "校驗日程變更", "Validate schedule changes", "校验日程变更喵", "校验日程变更",
        )
        put(
            StringKey.ProgressMeetingPreparation,
            "校验会议信息", "校驗會議資訊", "Validate meeting details", "校验会议信息喵", "校验会议信息",
        )
        put(
            StringKey.ProgressImageGeneration,
            "准备并生成图片", "準備並產生圖片", "Prepare and generate the image", "准备并生成图片喵", "准备并生成图片",
        )
        put(
            StringKey.ProgressImageReview,
            "审核图片相关性与安全性", "審核圖片相關性與安全性", "Review image relevance and safety",
            "审核图片相关性和安全性喵", "审核图片相关性与安全性",
        )
        put(
            StringKey.ProgressComponentAction,
            "执行已授权的组件能力", "執行已授權的元件能力", "Run an authorized component action",
            "执行已授权组件喵", "执行已授权的组件能力",
        )
        put(
            StringKey.ProgressSafetyNote,
            "仅显示可验证的处理阶段，不展示模型隐藏思维。",
            "僅顯示可驗證的處理階段，不展示模型隱藏思維。",
            "Shows verifiable processing stages, not hidden model reasoning.",
            "只显示可验证步骤，不展示隐藏思维喵。",
            "仅显示可验证处理阶段，不展示隐藏思维。",
        )
        put(StringKey.OrganizingAnswer, "马上就好", "馬上就好", "Almost ready", "马上就好喵", "马上完成")
        put(StringKey.OrganizingVerifiedAnswer, "马上整理好", "馬上整理好", "Almost ready", "马上整理好喵", "马上整理好")
        put(StringKey.WritingReviewing, "图片也快好了", "圖片也快好了", "Images are almost ready", "图片也快好了喵", "图片即将完成")
        put(
            StringKey.SearchingForSeconds,
            "已搜索 {0} 秒", "已搜尋 {0} 秒", "Searching for {0}s", "已经搜了 {0} 秒喵", "已搜索 {0} 秒",
        )
        put(
            StringKey.SearchCompletedIn,
            "搜索 {0} 秒", "搜尋 {0} 秒", "Searched in {0}s", "搜索用了 {0} 秒喵", "搜索 {0} 秒",
        )
        put(
            StringKey.SearchCompleteMeta,
            "{0} 个来源 · 搜索 {1} 秒", "{0} 個來源 · 搜尋 {1} 秒", "{0} sources · {1}s search",
            "{0} 个来源 · 搜索 {1} 秒喵", "{0} 个来源 · 搜索 {1} 秒",
        )
        put(
            StringKey.PaintingUnderstand,
            "正在理解画面中的主体与氛围", "正在理解畫面中的主體與氛圍", "Understanding the subject and mood",
            "正在理解画面和氛围喵", "正在理解主体与氛围",
        )
        put(
            StringKey.PaintingCompose,
            "正在搭建构图与视觉层次", "正在建立構圖與視覺層次", "Building the composition and visual layers",
            "正在搭建构图和层次喵", "正在构建构图与层次",
        )
        put(
            StringKey.PaintingDetail,
            "正在细化线条、色彩和光影", "正在細化線條、色彩和光影", "Refining lines, color, and lighting",
            "正在细化线条、颜色和光影喵", "正在细化线条、色彩和光影",
        )
        put(
            StringKey.PaintingReveal,
            "画面正在逐层显影", "畫面正在逐層顯影", "Bringing the image into view",
            "画面正在慢慢显影喵", "画面正在显影",
        )
        put(
            StringKey.PaintingWait,
            "图片工坊正在绘制，请稍候", "圖片工坊正在繪製，請稍候", "The image studio is drawing. Please wait",
            "图片工坊正在画画，请稍等喵", "图片工坊正在绘制。请稍候",
        )

        // ---- 主动提醒 ----
        put(StringKey.Reminders, "主动提醒", "主動提醒", "Reminders", "小提醒", "主动提醒")
        put(StringKey.NoReminders, "暂无提醒", "暫無提醒", "No reminders", "现在没有提醒喵", "暂无提醒")
        put(StringKey.RefreshReminders, "刷新提醒", "重新整理提醒", "Refresh reminders", "刷新一下喵", "刷新提醒")
        put(StringKey.HandleSuggestion, "去处理", "去處理", "Handle it", "去处理喵", "去处理")
        put(StringKey.Later, "稍后", "稍後", "Later", "等一下", "稍后")
        put(StringKey.Ignore, "忽略", "忽略", "Ignore", "不用啦", "忽略")
        put(StringKey.RemindLaterAt, "{0} 再提醒", "{0} 再提醒", "Remind at {0}", "{0} 再喊你喵", "{0} 再提醒")
        put(
            StringKey.ReminderOperationFailed,
            "操作失败，请稍后重试", "操作失敗，請稍後重試", "Action failed. Please try again",
            "没成功呢，再试一次喵", "操作失败，请稍后重试",
        )

        // ---- 游客与退出 ----
        put(StringKey.LoginAsGuest, "先以游客身份体验", "先以訪客身分體驗", "Continue as guest", "先当游客逛逛喵", "以游客身份体验")
        put(StringKey.GuestBadge, "游客", "訪客", "Guest", "游客喵", "游客")
        put(
            StringKey.GuestUpgradeHint,
            "游客数据仅保存在本次会话，登录后可长期保留",
            "訪客資料僅保存在本次工作階段，登入後可長期保留",
            "Guest data lives in this session only. Sign in to keep it.",
            "游客的东西只留在这次喵，登录才收得住",
            "游客数据仅本次会话有效，登录后长期保留。",
        )
        put(
            StringKey.ExitConfirmToast,
            "再按一次返回退出", "再按一次返回離開", "Press back again to exit",
            "再按一次就走啦喵", "再按一次返回退出",
        )
        put(StringKey.LoginOr, "或", "或", "or", "或者喵", "或")
        put(
            StringKey.GuestSignInCta,
            "登录账号", "登入帳號", "Sign in", "去登录喵", "登录账号",
        )
        put(
            StringKey.GuestProfileNotice,
            "你正在以游客身份使用，登录后可解锁全部技能并云端保存记录",
            "你正在以訪客身分使用，登入後可解鎖全部技能並雲端保存記錄",
            "You're browsing as a guest. Sign in to unlock all skills and sync your history.",
            "现在是游客喵，登录之后全部技能都能玩，记录也存得住",
            "当前为游客身份。登录后解锁全部技能并同步记录。",
        )

        // ---- 回答操作 ----
        put(
            StringKey.CopyPlainText,
            "复制纯文字", "複製純文字", "Copy text", "把字带走喵", "复制纯文字",
        )
        put(
            StringKey.CopiedToClipboard,
            "已复制到剪贴板", "已複製到剪貼簿", "Copied to clipboard",
            "复制好啦喵", "已复制到剪贴板",
        )
        put(
            StringKey.SaveAsImage,
            "保存图片", "儲存圖片", "Save image", "存成图片喵", "保存图片",
        )
        put(StringKey.Saving, "保存中…", "儲存中…", "Saving…", "存着喵…", "保存中…")
        put(
            StringKey.SaveImageFailed,
            "保存失败，请稍后重试", "儲存失敗，請稍後重試", "Save failed, please retry",
            "没存上喵，再试一次", "保存失败，请稍后重试。",
        )

        // ---- 底部导航 ----
        put(StringKey.TabChat, "聊天", "聊天", "Chat", "聊天", "聊天")
        put(StringKey.TabSkills, "技能", "技能", "Skills", "小背包", "技能")
        put(StringKey.TabCalendar, "日程", "日程", "Calendar", "日程", "日程")
        put(StringKey.TabReading, "阅读", "閱讀", "Reading", "读物", "阅读")
        put(StringKey.TabProfile, "我的", "我的", "Me", "我的", "我的")

        // ---- 聊天 ----
        put(
            StringKey.AppTagline,
            "一只有温度的大橘", "一隻有溫度的大橘", "A warm ginger cat",
            "一只有温度的大橘喵~", "一只有温度的大橘。",
        )
        put(
            StringKey.ChatIntro,
            "和我对话即可。我能主动理解任务，支持旅游规划、会议创建、新闻搜索、翻译、论文助读与 AI 生图。",
            "和我對話即可。我能主動理解任務，支援旅遊規劃、會議建立、新聞搜尋、翻譯、論文助讀與 AI 生圖。",
            "Just talk to me. I plan trips, create meetings, search news, translate, read papers and paint.",
            "和我说说话就好啦。旅行、会议、新闻、翻译、论文、画画，我都能帮你喵~",
            "直接对话即可。支持行程、会议、搜索、翻译、论文与生图。",
        )
        put(StringKey.ChatInputHint, "输入消息…", "輸入訊息…", "Message Floris…", "想说点什么喵…", "输入消息。")
        put(StringKey.ChatStop, "停止", "停止", "Stop", "先停一下", "停止")
        put(StringKey.ChatNew, "新对话", "新對話", "New chat", "新的一页", "新对话")
        put(StringKey.ChatHistory, "历史记录", "歷史紀錄", "History", "旧纸页", "历史记录")
        put(
            StringKey.SuggestNews,
            "最近 AI 有什么新进展", "最近 AI 有什麼新進展", "What's new in AI lately",
            "最近 AI 有什么新鲜事喵", "最近 AI 有什么新进展",
        )
        put(
            StringKey.SuggestBooks,
            "推荐几本明朝历史的书", "推薦幾本明朝歷史的書", "Recommend books on Ming history",
            "推荐几本明朝的书喵", "推荐几本明朝历史的书",
        )
        put(
            StringKey.SuggestPlace,
            "我附近有什么好玩的", "我附近有什麼好玩的", "What's fun near me",
            "我附近有什么好玩的喵", "我附近有什么好玩的",
        )
        put(
            StringKey.SuggestCode,
            "用 Python 写一个快速排序", "用 Python 寫一個快速排序", "Write quicksort in Python",
            "用 Python 写个快排喵", "用 Python 写一个快速排序",
        )
        put(StringKey.ChatSources, "来源", "來源", "Sources", "线索来源", "来源")
        put(
            StringKey.ChatEmptyHistoryTitle,
            "暂无历史对话", "暫無歷史對話", "No conversations yet",
            "还没有旧纸页喵", "暂无历史对话",
        )
        put(
            StringKey.ChatEmptyHistoryBody,
            "开始一段新对话，它会自动保存在这里",
            "開始一段新對話，它會自動保存在這裡",
            "Start a new chat and it will be saved here",
            "先聊一句吧，我会替你收好的喵",
            "开始新对话后会保存在此。",
        )

        // ---- 新手介绍（与网页端逐字一致）----
        put(
            StringKey.OnboardingWelcomeTitle,
            "欢迎来到 Floris 的小窝~", "歡迎來到 Floris 的小窩~", "Welcome to Floris’s little home",
            "欢迎来到 Floris 的小窝喵~", "欢迎来到 Floris 的小窝。",
        )
        put(
            StringKey.OnboardingOwners,
            "我的主人是 Jurant 和 Jimmy（相视一笑 😄）",
            "我的主人是 Jurant 和 Jimmy（相視一笑 😄）",
            "My humans are Jurant and Jimmy (they exchange a smile 😄).",
            "我的主人是 Jurant 和 Jimmy（相视一笑，尾巴也晃了晃 😄）",
            "我的主人是 Jurant 和 Jimmy（相视一笑 😄）。",
        )
        put(
            StringKey.OnboardingGithubWelcome,
            "欢迎光顾我的 GitHub，这里有我的功能说明喵~",
            "歡迎光顧我的 GitHub，這裡有我的功能說明喵~",
            "You are welcome to visit my GitHub for the full feature guide.",
            "欢迎光顾我的 GitHub，功能说明都整整齐齐放在那里喵~",
            "GitHub 中有完整的功能说明。",
        )
        put(
            StringKey.OnboardingIntroOffer,
            "当然，对于新人，我也会做详细的介绍（揣手手）",
            "當然，第一次來的客人也會得到詳細介紹（揣手手）",
            "Of course, I can give every newcomer a proper tour (paws tucked in).",
            "第一次来不用担心，我会慢慢介绍给你（乖乖揣手手）",
            "第一次来，我会带你看一遍（揣手手）。",
        )
        put(StringKey.OnboardingStart, "开始介绍", "開始介紹", "Start the tour", "开始逛小窝", "开始介绍")
        put(StringKey.OnboardingSkip, "算了不必了", "暫時不用", "No, thanks", "先不用啦", "不必")
        put(
            StringKey.OnboardingNewConversation,
            "点击这里开始一个新对话吧。Floris 已经把纸页铺好，正等你写下第一句话。",
            "點擊這裡開始一個新對話吧。Floris 已經把紙頁鋪好，正等你寫下第一句話。",
            "Start a fresh conversation here. Floris has opened a clean page for your first line.",
            "点击这里开始一个新对话吧。（把空白纸页推到你面前）",
            "点击这里开始新对话。空白页已经准备好。",
        )
        put(
            StringKey.OnboardingHistory,
            "这里可以看到历史对话哦。之前聊过的线索，我都替你按时间收在这里了。",
            "這裡可以看到歷史對話。之前聊過的線索，我都替你按時間收在這裡了。",
            "Your conversation history lives here, neatly arranged by time.",
            "喵，这里可以看到历史对话哦。（用爪尖轻轻点了点旧纸页）",
            "这里是历史对话，过去的内容按时间排列。",
        )
        put(
            StringKey.OnboardingMap,
            "地图会接住地点、当前位置和路线结果。说一句想去哪里，我就把它们落到真实地图上。",
            "地圖會接住地點、目前位置和路線結果。說一句想去哪裡，我就把它們放到真實地圖上。",
            "The map holds places, your current location, and route results from the conversation.",
            "地点和路线会落在这张地图上。（耳朵朝目的地方向转了转）",
            "这里展示地点、当前位置与路线结果。",
        )
        put(
            StringKey.OnboardingCalendar,
            "这是日历。它和地图可以联动安排出发与到达，也能独立管理每一条日程。",
            "這是日曆。它能和地圖聯動安排出發與抵達，也能獨立管理每一項日程。",
            "The calendar can work with maps for travel timing, while still managing schedules independently.",
            "日程住在这里；需要赶路时会牵起地图的手，平时也能自己好好工作。",
            "日历可与地图联动，也能独立管理日程。",
        )
        put(
            StringKey.OnboardingReading,
            "论文和文档可以收进“我的阅读”。需要再看时，不必回头翻很久。",
            "論文和文件可以收進「我的閱讀」。需要再看時，不必回頭翻很久。",
            "Save papers and documents in My Reading so they are easy to find again.",
            "读过的论文和文档会收在这里。（把书角认真压平）",
            "论文与文档可保存到“我的阅读”。",
        )
        put(
            StringKey.OnboardingReminders,
            "提醒与顶部问候是同一套主动式服务：重要事项排在前面，空闲时则留下一句轻轻的问候。",
            "提醒與頂部問候是同一套主動式服務：重要事項優先，空閒時會留下一句輕輕的問候。",
            "Reminders and the header ticker work together: important items come first, with gentle notes in quiet moments.",
            "提醒和顶上的小话会彼此照应。重要的事先来，没事时就摇着尾巴留一句小话。",
            "提醒与顶部问候联动；重要事项优先显示。",
        )
        put(
            StringKey.OnboardingSkills,
            "在 Skills 广场里可以决定 Floris 要带哪些本领出门；关闭的能力会在逻辑层直接停下。",
            "在 Skills 廣場可以決定 Floris 要帶哪些本領出門；關閉的能力會在邏輯層直接停止。",
            "Choose Floris’s capabilities in the Skills marketplace. Disabled skills stop at the logic layer.",
            "这里像我的小背包，想让我带哪项本领就打开哪一格。",
            "Skills 广场控制可用能力；关闭后会在逻辑层停止。",
        )
        put(
            StringKey.OnboardingSettings,
            "设置里能调整语言、搜索数量和其他偏好。想再看一次介绍，也从这里打开。",
            "設定中可以調整語言、搜尋數量和其他偏好；也能從這裡重開介紹。",
            "Settings contains language, search limits, other preferences, and this tour.",
            "偏好都收在设置里。以后想再逛一次小窝，也来这里找我。",
            "在设置中调整偏好，也可重新开启介绍。",
        )
        put(
            StringKey.OnboardingTheme,
            "点一下太阳或月亮，就能在白天与黑夜之间切换。两套颜色都替眼睛留了舒服的位置。",
            "點一下太陽或月亮，就能在白天與黑夜之間切換；兩套配色都照顧閱讀舒適度。",
            "Use the sun or moon to switch between light and dark themes.",
            "太阳和月亮藏在这里。（瞳孔跟着光线悄悄变圆）",
            "这里切换白天与黑夜主题。",
        )
        put(
            StringKey.OnboardingGithub,
            "欢迎光临我的 github 查看功能文档喵~",
            "歡迎光臨我的 GitHub 查看功能文件喵~",
            "Visit my GitHub to read the feature documentation.",
            "欢迎光临我的 github 查看功能文档喵~",
            "欢迎前往 GitHub 查看功能文档。",
        )
        put(StringKey.OnboardingNext, "下一站", "下一站", "Next stop", "去下一站", "下一步")
        put(StringKey.OnboardingFinish, "逛完啦", "逛完了", "Finish", "小窝逛完啦", "完成")
        put(
            StringKey.OnboardingSkipHint,
            "已经替你收好啦。想再看一次介绍，可在「我的 → 设置」重新开启。",
            "已經替你收好啦。想再看一次介紹，可在「我的 → 設定」重新開啟。",
            "All tucked away. Replay the tour anytime from Me → Settings.",
            "好哒，我先把介绍收起来。想再看就去「我的 → 设置」找我喵。",
            "介绍已关闭。可在「我的 → 设置」重新开启。",
        )
        put(StringKey.OnboardingGotIt, "知道啦", "知道了", "Got it", "记住啦", "知道了")
        put(
            StringKey.OnboardingChatInput,
            "想说什么就打在这里喵，也能夹一张图片给我看。",
            "想說什麼就打在這裡喵，也能夾一張圖片給我看。",
            "Type anything here — you can attach an image too.",
            "想说什么就打在这里喵，也能夹一张图片给我看。",
            "在此输入内容，支持附加图片。",
        )
        put(
            StringKey.OnboardingProfileCenter,
            "这里是你的个人中心，账号、用量和偏好都收在这儿喵。",
            "這裡是你的個人中心，帳號、用量和偏好都收在這兒喵。",
            "Your profile lives here — account, usage and preferences.",
            "这里是你的个人中心，账号、用量和偏好都收在这儿喵。",
            "个人中心：账号、用量与偏好。",
        )

        // ---- Skills ----
        put(StringKey.SkillsEyebrow, "AGENT SKILLS", "AGENT SKILLS", "AGENT SKILLS", "AGENT SKILLS", "AGENT SKILLS")
        put(
            StringKey.SkillsTitle,
            "组合你的 Floris 能力", "組合你的 Floris 能力", "Compose your Floris",
            "给我装上想要的本领喵", "组合可用能力",
        )
        put(
            StringKey.SkillsSubtitle,
            "只保留官方与已验证技能，按场景组合。",
            "只保留官方與已驗證技能，依場景組合。",
            "Official and verified skills only, composed by scenario.",
            "都是验证过的本领，按需要打开就好喵。",
            "仅保留官方与已验证技能。",
        )
        put(
            StringKey.SkillsSearchHint,
            "搜索技能、接口或标签…", "搜尋技能、介面或標籤…", "Search skills, APIs or tags…",
            "找找想要的本领喵…", "搜索技能、接口或标签。",
        )
        put(StringKey.SkillsEnabledCount, "已开启 {0}/{1}", "已開啟 {0}/{1}", "{0}/{1} on", "开了 {0}/{1} 格", "已开启 {0}/{1}")
        put(StringKey.SkillsAlwaysOn, "始终启用", "始終啟用", "Always on", "一直带着", "始终启用")
        put(StringKey.SkillsGuestReady, "游客可用", "訪客可用", "Guest ready", "客人也能用", "游客可用")
        put(StringKey.SkillsRequires, "需要先启用：{0}", "需要先啟用：{0}", "Requires: {0}", "得先打开：{0}", "需要先启用：{0}")
        put(StringKey.SkillsDependencies, "依赖", "依賴", "Dependencies", "牵着的手", "依赖")
        put(StringKey.SkillsComponentApi, "组件 API", "元件 API", "Component API", "组件 API", "组件 API")
        put(
            StringKey.SkillsLoginRequired,
            "需登录", "需登入", "Sign in required", "要登录喵", "需登录",
        )
        put(
            StringKey.SkillsLoginHint,
            "登录后即可启用此技能",
            "登入後即可啟用此技能",
            "Sign in to enable this skill.",
            "登录之后就能开啦喵",
            "登录后可启用此技能。",
        )
        put(
            StringKey.SkillsGuestNotice,
            "游客可使用通用问答与主动式 Agent，其余技能登录后解锁",
            "訪客可使用通用問答與主動式 Agent，其餘技能登入後解鎖",
            "Guests can use general chat and the proactive agent. Sign in for the rest.",
            "游客只能玩通用问答和主动小助手喵，其他要登录",
            "游客可用通用问答与主动式 Agent，其余技能需登录。",
        )

        // ---- 日程 ----
        put(StringKey.CalendarTitle, "日程", "日程", "Calendar", "日程", "日程")
        put(StringKey.CalendarToday, "今天", "今天", "Today", "今天", "今天")
        put(
            StringKey.CalendarDayEmpty,
            "这一天还没有安排", "這一天還沒有安排", "Nothing scheduled",
            "这天空着呢喵", "这一天没有安排。",
        )
        put(StringKey.CalendarEmptyTitle, "暂无日程", "暫無日程", "No schedules", "还没有日程喵", "暂无日程")
        put(
            StringKey.CalendarEmptyBody,
            "在聊天中让 Floris 帮你安排，确认后会出现在这里",
            "在聊天中讓 Floris 幫你安排，確認後會出現在這裡",
            "Ask Floris in chat; confirmed items appear here",
            "跟我说一声，我安排好你确认就会出现在这里喵",
            "在聊天中安排，确认后显示于此。",
        )

        // ---- 阅读 ----
        put(StringKey.ReadingTitle, "我的阅读", "我的閱讀", "My Reading", "我的读物", "我的阅读")
        put(
            StringKey.ReadingSearchHint,
            "检索论文主题或作者…", "檢索論文主題或作者…", "Search papers by topic or author…",
            "找找论文喵…", "检索论文主题或作者。",
        )
        put(StringKey.ReadingLibrary, "阅读库", "閱讀庫", "Library", "小书架", "阅读库")
        put(StringKey.ReadingEmptyTitle, "论文与文档助读", "論文與文件助讀", "Papers & documents", "论文助读喵", "论文与文档助读")
        put(
            StringKey.ReadingEmptyBody,
            "检索经过验证的学术记录，或在聊天里让 Floris 帮你读",
            "檢索經過驗證的學術紀錄，或在聊天裡讓 Floris 幫你讀",
            "Search verified academic records, or ask Floris to read for you",
            "我可以帮你找论文，也可以念给你听喵",
            "检索学术记录，或在聊天中委托阅读。",
        )
        put(StringKey.ReadingSummarize, "总结要点", "總結要點", "Summarize", "帮我总结", "总结要点")
        put(StringKey.ReadingTranslate, "翻译全文", "翻譯全文", "Translate", "翻译一下", "翻译全文")
        put(
            StringKey.ReadingNoResultTitle,
            "没有找到相关论文", "沒有找到相關論文", "No papers found",
            "没找到呢喵", "没有找到相关论文",
        )
        put(
            StringKey.ReadingNoResultBody,
            "换个关键词试试", "換個關鍵詞試試", "Try another keyword",
            "换个词再找找喵", "请更换关键词。",
        )

        // ---- 地图 ----
        put(StringKey.MapTitle, "地图", "地圖", "Map", "地图", "地图")
        put(
            StringKey.MapSearchHint,
            "搜索真实地点…", "搜尋真實地點…", "Search real places…",
            "找个地方喵…", "搜索真实地点。",
        )
        put(StringKey.MapPlaces, "地点 · {0}", "地點 · {0}", "{0} places", "{0} 个地方", "地点 · {0}")
        put(StringKey.MapRoute, "路线规划", "路線規劃", "Routes", "怎么走", "路线规划")
        put(StringKey.MapEmptyTitle, "地图工作区", "地圖工作區", "Map workspace", "地图小窝", "地图工作区")
        put(
            StringKey.MapEmptyBody,
            "在聊天中让 Floris 推荐地点，或直接搜索真实地点",
            "在聊天中讓 Floris 推薦地點，或直接搜尋真實地點",
            "Ask Floris for places in chat, or search directly",
            "让我推荐地方，或者你自己找找喵",
            "在聊天中获取推荐，或直接搜索。",
        )
        put(StringKey.MapShowOnMap, "查看地点", "查看地點", "Show on map", "去地图看看", "查看地点")

        // ---- 个人中心 ----
        put(StringKey.ProfileTitle, "我的", "我的", "Me", "我的", "我的")
        put(StringKey.ProfileBriefs, "主动提醒", "主動提醒", "Proactive notes", "小话", "主动提醒")
        put(StringKey.ProfileWorkspace, "工作区", "工作區", "Workspace", "小窝", "工作区")
        put(StringKey.ProfileAccount, "账号", "帳號", "Account", "账号", "账号")
        put(StringKey.ProfileSettings, "设置", "設定", "Settings", "设置", "设置")
        put(StringKey.ProfileAbout, "关于", "關於", "About", "关于我", "关于")
        put(StringKey.ProfileSignOut, "退出登录", "登出", "Sign out", "先走一步", "退出登录")
        put(StringKey.ProfileMap, "地图工作区", "地圖工作區", "Map workspace", "地图小窝", "地图工作区")
        put(StringKey.ProfileReading, "我的阅读", "我的閱讀", "My Reading", "我的读物", "我的阅读")

        // ---- 设置 ----
        put(StringKey.SettingsTitle, "设置", "設定", "Settings", "设置", "设置")
        put(StringKey.SettingsAppearance, "外观", "外觀", "Appearance", "样子", "外观")
        put(StringKey.SettingsTheme, "主题", "主題", "Theme", "白天黑夜", "主题")
        put(StringKey.SettingsThemeSystem, "跟随系统", "跟隨系統", "System", "跟着手机", "跟随系统")
        put(StringKey.SettingsThemeLight, "白天", "白天", "Light", "白天", "白天")
        put(StringKey.SettingsThemeDark, "黑夜", "黑夜", "Dark", "黑夜", "黑夜")
        put(StringKey.SettingsLanguage, "界面语言", "介面語言", "Language", "说话方式", "界面语言")
        put(StringKey.SettingsPreferences, "偏好", "偏好", "Preferences", "小习惯", "偏好")
        put(StringKey.SettingsProactive, "主动提醒", "主動提醒", "Proactive notes", "主动小话", "主动提醒")
        put(
            StringKey.SettingsProactiveDesc,
            "日程变化、天气与行程的主动播报",
            "日程變化、天氣與行程的主動播報",
            "Proactive notes about schedules, weather and trips",
            "有事我会先跟你说一声喵",
            "日程、天气与行程的主动播报。",
        )
        put(StringKey.SettingsWebResults, "网页结果数量", "網頁結果數量", "Web results", "找几条网页", "网页结果数量")
        put(
            StringKey.SettingsWebResultsDesc,
            "调低可以更快出结果", "調低可以更快出結果", "Lower is faster",
            "调少一点我跑得更快喵", "调低可加快响应。",
        )
        put(StringKey.SettingsImageCandidates, "候选图片数量", "候選圖片數量", "Image candidates", "找几张图", "候选图片数量")
        put(
            StringKey.SettingsImageCandidatesDesc,
            "设为 0 可关闭富搜索配图", "設為 0 可關閉富搜尋配圖", "Set to 0 to disable rich images",
            "设成 0 就不配图啦喵", "设为 0 关闭配图。",
        )
        put(StringKey.SettingsReplayTour, "新人介绍", "新人介紹", "Feature tour", "再逛一次小窝", "新人介绍")
        put(
            StringKey.SettingsReplayTourDesc,
            "重新观看 Floris 的功能引导", "重新觀看 Floris 的功能引導", "Replay the Floris feature tour",
            "我再带你逛一遍喵", "重新观看功能引导。",
        )
        put(StringKey.SettingsUsage, "用量", "用量", "Usage", "用了多少", "用量")
        put(StringKey.SettingsDailyTokens, "今日 Token", "今日 Token", "Today", "今天用的", "今日 Token")
        put(StringKey.SettingsMonthlyTokens, "本月 Token", "本月 Token", "This month", "这个月用的", "本月 Token")
        put(StringKey.SettingsData, "数据", "資料", "Data", "东西", "数据")
        put(StringKey.SettingsResetData, "清除全部数据", "清除全部資料", "Erase all data", "全部收拾掉", "清除全部数据")
        put(StringKey.SettingsResetTitle, "清除全部数据？", "清除全部資料？", "Erase all data?", "真的全部收拾掉吗？", "清除全部数据？")
        put(
            StringKey.SettingsResetBody,
            "将删除账号下的全部会话、工作区与文件，且无法恢复。",
            "將刪除帳號下的全部對話、工作區與檔案，且無法復原。",
            "This permanently deletes all conversations, workspaces and files.",
            "所有纸页和小东西都会不见，捡不回来的喵…",
            "将永久删除全部会话、工作区与文件。",
        )
        put(StringKey.SettingsResetConfirm, "确认清除", "確認清除", "Erase", "确认收拾", "确认清除")
        put(StringKey.SettingsNickname, "昵称", "暱稱", "Display name", "怎么叫你", "昵称")
        put(StringKey.SettingsNotSet, "未设置", "未設定", "Not set", "还没取名", "未设置")

        // ---- 登录 ----
        put(StringKey.LoginEmail, "邮箱", "電子郵件", "Email", "邮箱", "邮箱")
        put(StringKey.LoginSendCode, "发送验证码", "發送驗證碼", "Send code", "给我验证码", "发送验证码")
        put(StringKey.LoginSending, "发送中…", "發送中…", "Sending…", "正在送出…", "发送中…")
        put(StringKey.LoginCode, "验证码", "驗證碼", "Code", "验证码", "验证码")
        put(StringKey.LoginSignIn, "登录", "登入", "Sign in", "进小窝", "登录")
        put(StringKey.LoginSigningIn, "登录中…", "登入中…", "Signing in…", "正在开门…", "登录中…")
        put(StringKey.LoginBackToEmail, "返回修改邮箱", "返回修改郵箱", "Change email", "改个邮箱", "返回修改邮箱")
        put(StringKey.LoginCodeSentTo, "验证码已发送至", "驗證碼已發送至", "Code sent to", "验证码送到了", "验证码已发送至")

        // ---- 工作区动作 ----
        put(StringKey.ActionAwaiting, "待确认", "待確認", "Needs confirmation", "等你点头", "待确认")
        put(StringKey.ActionReady, "待处理", "待處理", "Ready", "准备好了", "待处理")
        put(StringKey.ActionActive, "进行中", "進行中", "Active", "正在忙", "进行中")
        put(StringKey.ActionExecuting, "执行中", "執行中", "Executing", "正在做", "执行中")
        put(StringKey.ActionSucceeded, "已完成", "已完成", "Done", "办好啦", "已完成")
        put(StringKey.ActionFailed, "失败", "失敗", "Failed", "没成功", "失败")
        put(StringKey.ActionCancelled, "已取消", "已取消", "Cancelled", "算了", "已取消")
        put(StringKey.ActionNeedsReview, "需要核对", "需要核對", "Needs review", "要再看看", "需要核对")
        put(
            StringKey.ActionUnknown,
            "收到新版组件，请升级客户端查看",
            "收到新版元件，請升級用戶端查看",
            "New component received — please update the app",
            "这是新玩意，我还看不懂喵，升级一下吧",
            "新版组件，请升级客户端。",
        )
        put(StringKey.ClarificationSubmit, "确认并继续", "確認並繼續", "Continue", "就这样继续", "确认并继续")
        put(StringKey.ClarificationSubmitting, "提交中…", "提交中…", "Submitting…", "正在递上去…", "提交中…")
    }

    fun of(key: StringKey, language: Language): String =
        catalog[key]?.getOrNull(language.index) ?: catalog[key]?.firstOrNull() ?: key.name
}
