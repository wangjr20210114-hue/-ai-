package com.floris.android.ui.prefs

/** 文案键。每条必须提供全部五种语言，避免静默回退。 */
enum class StringKey {
    // 通用
    Confirm, Cancel, Retry, Done, Close, Search, Loading, Failed, Back, Delete, Edit, Send,
    Self, Decrease, Increase, QuoteOne, QuoteTwo, QuoteThree, QuoteFour, QuoteFive,
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
    RemindLaterAt, ReminderOperationFailed, NotificationChannelName, NotificationChannelDescription,
    // 会话内主动提醒（与网页端 ProactiveRenderer 对齐）
    ChatProactiveHandle, ChatProactiveSnooze, HelpMeHandle,
    ChatProactiveOngoing, ChatProactiveAwaiting, ChatProactiveCurrentStep, ChatProactiveSyncing,
    // 游客与退出
    LoginAsGuest, GuestBadge, GuestUpgradeHint, ExitConfirmToast,
    LoginOr, GuestSignInCta, GuestProfileNotice,
    FeatureSignInRequired, FeatureSkillDisabled, FeatureUnavailable, FeatureOpenSkills,
    // 回答操作
    CopyPlainText, CopiedToClipboard, SaveAsImage, Saving, SaveImageFailed, SavedToGallery,
    // 个人信息
    AccountTitle, AccountMembership, AccountHelp, AccountAboutDesc,
    // 澄清卡
    ClarificationAnswered,
    // 底部导航
    TabChat, TabSkills, TabCalendar, TabReading, TabProfile,
    // 聊天
    AppTagline, ChatIntro, ChatInputHint, ChatStop, ChatNew, ChatHistory,
    SuggestNews, SuggestBooks, SuggestPlace, SuggestCode,
    ChatSources, ChatEmptyHistoryTitle, ChatEmptyHistoryBody,
    ChatSourceCount, PaperCited, LocationPermissionTitle, LocationPermissionBody,
    AttachedImageCount, ActionMapTitle, ActionCalendarTitle, ActionMeetingTitle,
    ActionImageTitle, ActionWorkspaceTitle, ActionRouteMode, CalendarChangeAdd,
    CalendarChangeUpdate, MeetingSubject, MeetingTime, MeetingSubjectLabel,
    MeetingStartTime, MeetingEndTime, MeetingSaveCheck, MeetingAcceptWarning,
    MeetingJoin, MeetingCode, MeetingStartValue, TraceId, Unscheduled, Yes, No,
    SelectValue, InputPlaceholder,
    ChatQueueTitle, ChatQueueEdit, ChatQueueDelete, ChatQueueRunNow, ChatQueueFull,
    ChatRename, ChatRenameHint, ChatMessageCount, TimeJustNow, TimeMinutesAgo,
    TimeHoursAgo, TimeDaysAgo, ChatAddImage, ChatAddDocument, ChatUploadedDocument,
    ChatPaperOpened, ChatUploadFailed,
    ChatVoiceStart, ChatVoiceStop, ChatVoiceUnavailable,
    ChatCamera, SidebarOpen, SidebarNewChat, SidebarPlace,
    ImageEditHint, ImageEditAction, ImageOriginal, ImageUpdated, ImagePrompt,
    ImageSaveToGallery, ChatAddSchedule, RouteCalendarRequest,
    HintFreshness, HintFreshnessLogin, HintSkill, HintSkillLogin,
    ChatRestoreFailed, ChatConnectionInterrupted, ChatGenerationFailed,
    ChatImageFailed, OperationFailed, NetworkUnavailable, SessionExpired,
    LoginRequired, MembershipRequired, TooManyRequests, ServiceUnavailable,
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
    SkillsConflicts, SkillsRecommends, SkillCategoryFoundation, SkillCategoryKnowledge,
    SkillCategoryCreative, SkillCategoryProductivity, SkillCategoryLocation, SkillCategoryOther,
    SkillsLoginRequired, SkillsLoginHint, SkillsGuestNotice,
    SkillsAdd, SkillsImportTitle, SkillsImportUrl, SkillsImportName,
    SkillsImportDescription, SkillsImportInstructions, SkillsImport, SkillsChooseFile,
    SkillsPrivate, SkillsRemove, SkillsUploads, SkillsSubmitReview, SkillsPendingReview,
    SkillsApproved, SkillsRejected, SkillsStored,
    SkillsConnection, SkillsConnectionToken, SkillsConnect, SkillsConnected, SkillsDisconnect,
    SkillsMarketFailed, SkillsEmptyTitle, SkillsEmptyBody, SkillsOperationFailed,
    SkillsImportFailed, SkillsSubmitFailed, SkillsConnectFailed, SkillsDisconnectFailed,
    SkillsOfficial, SkillsComponentApiHint, SkillsComponentApiVersion,
    SkillsComponentApiParameters, SkillsComponentApiExample,
    // 日程
    CalendarTitle, CalendarToday, CalendarDayEmpty, CalendarEmptyTitle, CalendarEmptyBody,
    CalendarAdd, CalendarEdit, CalendarDelete, CalendarEventTitle, CalendarLocation,
    CalendarStart, CalendarDuration, CalendarSave,
    CalendarYearMonth, CalendarPreviousMonth, CalendarNextMonth, CalendarOnline,
    CalendarLoadFailed, CalendarSaveFailed, CalendarDeleteFailed,
    WeekMonday, WeekTuesday, WeekWednesday, WeekThursday, WeekFriday, WeekSaturday, WeekSunday,
    // 阅读
    ReadingTitle, ReadingSearchHint, ReadingLibrary, ReadingEmptyTitle, ReadingEmptyBody,
    ReadingSummarize, ReadingTranslate, ReadingNoResultTitle, ReadingNoResultBody,
    ReadingUpload, ReadingUploading, ReadingSave, ReadingSaved, ReadingDelete, ReadingUploadFailed,
    ReadingResults, ReadingAutoOrganize, ReadingFolderNew, ReadingFolderRename,
    ReadingFolderDelete, ReadingAll, ReadingPaper, ReadingOpen, ReadingOpening,
    ReadingMove, ReadingAnalyze, ReadingAsk, ReadingAskHint, ReadingSaveResult,
    ReadingSearchFailed, ReadingSaveFailed, ReadingDeleteFailed, ReadingOperationFailed,
    ReadingOpenFailed, ReadingRunFailed, ReadingUntitledDocument, ReadingUntitledFolder,
    // 地图
    MapTitle, MapSearchHint, MapPlaces, MapRoute, MapEmptyTitle, MapEmptyBody, MapShowOnMap,
    MapNamedRoute, DurationHoursMinutes, DurationMinutes, MapSearchFailed,
    MapNeedTwoPlaces, MapServiceUnavailable, MapPlanFailed,
    // 个人中心
    ProfileTitle, ProfileBriefs, ProfileWorkspace, ProfileAccount, ProfileSettings,
    ProfileAbout, ProfileSignOut, ProfileMap, ProfileReading,
    ProfileDefaultUser, ProfileReadingDesc, ProfileMapDesc, ProfileSettingsDesc,
    ProfileAboutDesc, Important, MembershipPlus, MembershipPro, MembershipFree, MembershipGuest,
    ProfileAvatar, ProfileDefaultDisplayName, ProfileNameUpdated, ProfileUpdateFailed,
    ProfileAvatarUpdated, ProfileAvatarUpdateFailed, HistoryLoadFailed,
    // 设置
    SettingsTitle, SettingsAppearance, SettingsTheme, SettingsThemeSystem, SettingsThemeLight,
    SettingsThemeDark, SettingsLanguage, SettingsPreferences, SettingsProactive,
    SettingsProactiveDesc, SettingsWebResults, SettingsWebResultsDesc, SettingsImageCandidates,
    SettingsImageCandidatesDesc, SettingsReplayTour, SettingsReplayTourDesc, SettingsUsage,
    SettingsDailyTokens, SettingsMonthlyTokens, SettingsData, SettingsResetData,
    SettingsResetTitle, SettingsResetBody, SettingsResetConfirm, SettingsNickname, SettingsNotSet,
    SettingsResetting, SettingsParallelImages, SettingsParallelImagesDesc,
    SettingsMapExperience, SettingsMapExperienceDesc, SettingsMapServiceMode,
    SettingsMapFast, SettingsMapBalanced, SettingsMapComplete, SettingsMapPlaceCount,
    SettingsMapRouteStops, SettingsMapTimeout, SettingsPreferredRoute,
    SettingsRouteStrategy, SettingsNearTolerance, SettingsLearnRoute,
    RouteDriving, RouteTransit, RouteWalking, RouteBicycling, RouteBus, RouteSubway, RouteRail,
    StrategyTimeCost, StrategyLeastTime, StrategyLeastCost,
    SettingsPersonalization, SettingsPersonalizationDesc, PersonalizationTitle,
    MemorySection, MemoryEnabled, MemoryEnabledDesc, MemoryPending, MemorySaved,
    MemoryEmpty, MemoryReason, MemoryReject, MemoryRollback, MemoryClear,
    MemoryClearTitle, MemoryClearBody, RulesSection, ProactiveSection,
    ProactiveAutonomy, ProactiveObserve, ProactiveRemind, ProactivePropose,
    ProactiveLowRiskAuto, ProactiveQuietHours, ProactiveDailyLimit,
    ProactiveLookahead, ProactiveWindowLimit, ProactiveProviderLimit,
    ProactiveRouteGap, ProactiveTravelBuffer, WorkflowSection, WorkflowEmpty,
    WorkflowConfirm, WorkflowReject, WorkflowCancel, WorkflowCompleteStep,
    WorkflowSkipStep, WorkflowMarkFailed, WorkflowCompensationComplete,
    SettingsSaved, SettingsSaveFailed,
    SettingsResetSucceeded, SettingsResetFailed,
    // 登录
    LoginEmail, LoginSendCode, LoginSending, LoginCode, LoginSignIn, LoginSigningIn,
    LoginBackToEmail, LoginCodeSentTo, LoginInvalidEmail, LoginEnterCode, LoginOperationFailed,
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
        put(StringKey.Back, "返回", "返回", "Back", "回去", "返回")
        put(StringKey.Delete, "删除", "刪除", "Delete", "删掉", "删除")
        put(StringKey.Edit, "编辑", "編輯", "Edit", "改一下", "编辑")
        put(StringKey.Send, "发送", "傳送", "Send", "发出去", "发送")
        put(StringKey.Self, "我", "我", "Me", "我", "我")
        put(StringKey.Decrease, "减少", "減少", "Decrease", "少一点", "减少")
        put(StringKey.Increase, "增加", "增加", "Increase", "多一点", "增加")
        put(StringKey.QuoteOne, "把小事做好，时间会替你铺成路。", "把小事做好，時間會替你鋪成路。", "Small things done well become a path over time.", "把小事做好，时间会替你铺成路喵。", "把小事做好，时间会替你铺成路。")
        put(StringKey.QuoteTwo, "风会记得每一片认真生长的叶子。", "風會記得每一片認真生長的葉子。", "The wind remembers every leaf that kept growing.", "风会记得每片认真长大的叶子喵。", "风会记得认真生长的叶子。")
        put(StringKey.QuoteThree, "慢一点也没关系，星光总会找到夜路。", "慢一點也沒關係，星光總會找到夜路。", "It's fine to go slowly; starlight still finds the night road.", "慢一点没关系，星光会找到夜路喵。", "慢一点也没关系。")
        put(StringKey.QuoteFour, "留一点从容，给正在发生的好事。", "留一點從容，給正在發生的好事。", "Leave a little room for good things already unfolding.", "给正在发生的好事留点从容喵。", "给好事留一点从容。")
        put(StringKey.QuoteFive, "今天也要像大橘一样，稳稳地晒太阳。", "今天也要像大橘一樣，穩穩地曬太陽。", "Take in today's sunshine like a content orange cat.", "今天也像大橘一样稳稳晒太阳喵。", "今天也稳稳地晒太阳。")

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
        put(StringKey.ChatProactiveHandle, "帮我处理", "幫我處理", "Handle for me", "帮我处理喵", "帮我处理")
        put(StringKey.ChatProactiveSnooze, "一小时后提醒", "一小時後提醒", "Remind in 1 hour", "一小时后提醒喵", "一小时后提醒")
        put(StringKey.HelpMeHandle, "帮我处理：{0}", "幫我處理：{0}", "Handle for me: {0}", "帮我处理：{0} 喵", "帮我处理：{0}")
        put(StringKey.ChatProactiveOngoing, "进行中：{0}", "進行中：{0}", "In progress: {0}", "正在进行：{0}", "进行中：{0}")
        put(StringKey.ChatProactiveAwaiting, "待确认：{0}", "待確認：{0}", "Awaiting confirmation: {0}", "等你确认：{0}", "待确认：{0}")
        put(StringKey.ChatProactiveCurrentStep, "当前步骤：{0}", "目前步驟：{0}", "Current step: {0}", "现在这步：{0}", "当前步骤：{0}")
        put(StringKey.ChatProactiveSyncing, "计划同步中", "計畫同步中", "Syncing plan", "计划同步中喵", "计划同步中")
        put(
            StringKey.ReminderOperationFailed,
            "操作失败，请稍后重试", "操作失敗，請稍後重試", "Action failed. Please try again",
            "没成功呢，再试一次喵", "操作失败，请稍后重试",
        )
        put(StringKey.NotificationChannelName, "Floris 主动提醒", "Floris 主動提醒", "Floris reminders", "Floris 小提醒", "Floris 提醒")
        put(StringKey.NotificationChannelDescription, "日程、任务和出行提醒", "日程、任務和出行提醒", "Schedule, task and travel reminders", "日程、任务和出门提醒喵", "日程、任务和出行提醒")

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
            StringKey.FeatureSignInRequired,
            "登录后即可使用这里的完整功能",
            "登入後即可使用這裡的完整功能",
            "Sign in to use this feature.",
            "登录后就能用这个功能啦喵",
            "登录后可使用此功能。",
        )
        put(
            StringKey.FeatureSkillDisabled,
            "这个功能尚未开启，可在 Skills 中启用",
            "這個功能尚未啟用，可在 Skills 中開啟",
            "This feature is off. Enable it in Skills.",
            "这个功能还没打开喵，可以去 Skills 开启",
            "此功能尚未启用，请在 Skills 中开启。",
        )
        put(
            StringKey.FeatureUnavailable,
            "这个功能暂时不可用，请稍后再试",
            "這個功能暫時無法使用，請稍後再試",
            "This feature is temporarily unavailable. Try again later.",
            "这个功能暂时用不了喵，稍后再试",
            "此功能暂不可用，请稍后再试。",
        )
        put(
            StringKey.FeatureOpenSkills,
            "去开启", "去開啟", "Enable", "去打开", "去开启",
        )

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
            StringKey.ClarificationAnswered,
            "已选择：{0}", "已選擇：{0}", "Answered: {0}", "选好了喵：{0}", "已选择：{0}",
        )
        put(
            StringKey.AccountTitle,
            "个人信息", "個人資訊", "Account", "我的资料喵", "个人信息",
        )
        put(
            StringKey.AccountMembership,
            "会员等级", "會員等級", "Membership", "会员等级", "会员等级",
        )
        put(
            StringKey.AccountHelp,
            "帮助与介绍", "說明與介紹", "Help & intro", "帮我看看喵", "帮助与介绍",
        )
        put(
            StringKey.AccountAboutDesc,
            "查看完整功能说明", "查看完整功能說明", "Read the full feature guide",
            "看看我都会啥喵", "查看完整功能说明。",
        )
        put(
            StringKey.SaveImageFailed,
            "保存失败，请稍后重试", "儲存失敗，請稍後重試", "Save failed, please retry",
            "没存上喵，再试一次", "保存失败，请稍后重试。",
        )
        put(StringKey.SavedToGallery, "已保存到相册", "已儲存到相簿", "Saved to gallery", "已经存到相册啦喵", "已保存到相册")

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
        put(StringKey.ChatInputHint, "发消息…", "發訊息…", "Message Floris…", "发消息喵…", "发消息。")
        put(StringKey.ChatStop, "停止", "停止", "Stop", "先停一下", "停止")
        put(StringKey.ChatNew, "新对话", "新對話", "New chat", "新的一页", "新对话")
        put(StringKey.ChatHistory, "历史记录", "歷史紀錄", "History", "旧纸页", "历史记录")
        put(StringKey.ChatCamera, "拍照", "拍照", "Camera", "拍一张喵", "拍照")
        put(StringKey.SidebarOpen, "打开侧边栏", "開啟側邊欄", "Open sidebar", "打开抽屉喵", "打开侧边栏")
        put(StringKey.SidebarNewChat, "开启一个新对话", "開啟一個新對話", "Start a new chat", "开一页新的喵", "开启一个新对话")
        put(StringKey.SidebarPlace, "地点", "地點", "Places", "去哪儿", "地点")
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
        put(StringKey.ChatSourceCount, "{0} 个来源", "{0} 個來源", "{0} sources", "{0} 条线索", "{0} 个来源")
        put(StringKey.PaperCited, "被引 {0}", "被引 {0}", "Cited by {0}", "被引用 {0} 次", "被引 {0}")
        put(StringKey.LocationPermissionTitle, "需要你的位置", "需要你的位置", "Location needed", "可以告诉我你在哪吗", "需要位置权限")
        put(StringKey.LocationPermissionBody, "Floris 希望使用当前位置来提供更准确的结果。", "Floris 希望使用目前位置來提供更準確的結果。", "Floris can use your current location to improve the result.", "告诉我当前位置，结果会更准确喵。", "使用当前位置可提高结果准确度。")
        put(StringKey.AttachedImageCount, "已附 {0} 张图片", "已附 {0} 張圖片", "{0} images attached", "夹了 {0} 张图片", "已附 {0} 张图片")
        put(StringKey.ActionMapTitle, "地图推荐", "地圖推薦", "Map recommendation", "地图推荐", "地图推荐")
        put(StringKey.ActionCalendarTitle, "日程变更", "日程變更", "Calendar changes", "日程调整", "日程变更")
        put(StringKey.ActionMeetingTitle, "会议", "會議", "Meeting", "会议", "会议")
        put(StringKey.ActionImageTitle, "图片生成", "圖片生成", "Image generation", "图片工坊", "图片生成")
        put(StringKey.ActionWorkspaceTitle, "待处理事项", "待處理事項", "Workspace action", "等你确认的事", "待处理事项")
        put(StringKey.ActionRouteMode, "路线方式：{0}", "路線方式：{0}", "Route mode: {0}", "怎么走：{0}", "路线方式：{0}")
        put(StringKey.CalendarChangeAdd, "新增", "新增", "Add", "新增", "新增")
        put(StringKey.CalendarChangeUpdate, "更新", "更新", "Update", "更新", "更新")
        put(StringKey.MeetingSubject, "主题：{0}", "主題：{0}", "Subject: {0}", "主题：{0}", "主题：{0}")
        put(StringKey.MeetingTime, "时间：{0} ~ {1}", "時間：{0} ~ {1}", "Time: {0} – {1}", "时间：{0} 到 {1}", "时间：{0} ~ {1}")
        put(StringKey.MeetingSubjectLabel, "会议主题", "會議主題", "Meeting subject", "会议叫什么", "会议主题")
        put(StringKey.MeetingStartTime, "开始时间", "開始時間", "Start time", "什么时候开始", "开始时间")
        put(StringKey.MeetingEndTime, "结束时间", "結束時間", "End time", "什么时候结束", "结束时间")
        put(StringKey.MeetingSaveCheck, "保存并检查", "儲存並檢查", "Save and check", "保存再检查", "保存并校验")
        put(StringKey.MeetingAcceptWarning, "我已了解：{0}", "我已了解：{0}", "I understand: {0}", "知道啦：{0}", "确认风险：{0}")
        put(StringKey.MeetingJoin, "加入会议", "加入會議", "Join meeting", "去开会", "加入会议")
        put(StringKey.MeetingCode, "会议号：{0}", "會議號：{0}", "Meeting code: {0}", "会议号：{0}", "会议号：{0}")
        put(StringKey.MeetingStartValue, "开始时间：{0}", "開始時間：{0}", "Starts at: {0}", "开始时间：{0}", "开始时间：{0}")
        put(StringKey.TraceId, "追踪 ID：{0}", "追蹤 ID：{0}", "Trace ID: {0}", "追踪 ID：{0}", "追踪 ID：{0}")
        put(StringKey.Unscheduled, "未定", "未定", "Not set", "还没定", "未定")
        put(StringKey.Yes, "是", "是", "Yes", "是呀", "是")
        put(StringKey.No, "否", "否", "No", "不是", "否")
        put(StringKey.SelectValue, "选择{0}", "選擇{0}", "Choose {0}", "选一下{0}", "选择{0}")
        put(StringKey.InputPlaceholder, "请输入", "請輸入", "Enter a value", "写在这里", "请输入")
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
        put(StringKey.ChatQueueTitle, "待发送 {0}/5", "待傳送 {0}/5", "Queued {0}/5", "排队中 {0}/5 喵", "待发送 {0}/5")
        put(StringKey.ChatQueueEdit, "编辑", "編輯", "Edit", "改一下", "编辑")
        put(StringKey.ChatQueueDelete, "删除", "刪除", "Delete", "删掉", "删除")
        put(StringKey.ChatQueueRunNow, "立即发送", "立即傳送", "Send now", "现在发喵", "立即发送")
        put(StringKey.ChatQueueFull, "最多可排队 5 条消息", "最多可排隊 5 則訊息", "Up to 5 messages can be queued", "最多排 5 条喵", "最多可排队 5 条消息")
        put(StringKey.ChatRename, "重命名对话", "重新命名對話", "Rename chat", "给它换个名字", "重命名对话")
        put(StringKey.ChatRenameHint, "输入新名称", "輸入新名稱", "New chat name", "新名字写这里", "输入新名称")
        put(StringKey.ChatMessageCount, "{0} 条", "{0} 則", "{0} messages", "{0} 条喵", "{0} 条")
        put(StringKey.TimeJustNow, "刚刚", "剛剛", "Just now", "刚刚喵", "刚刚")
        put(StringKey.TimeMinutesAgo, "{0} 分钟前", "{0} 分鐘前", "{0} min ago", "{0} 分钟前喵", "{0} 分钟前")
        put(StringKey.TimeHoursAgo, "{0} 小时前", "{0} 小時前", "{0} hr ago", "{0} 小时前喵", "{0} 小时前")
        put(StringKey.TimeDaysAgo, "{0} 天前", "{0} 天前", "{0} days ago", "{0} 天前喵", "{0} 天前")
        put(StringKey.ChatAddImage, "添加图片", "新增圖片", "Add image", "加张图片", "添加图片")
        put(StringKey.ChatAddDocument, "上传文档", "上傳文件", "Upload document", "传个文档", "上传文档")
        put(StringKey.ChatUploadedDocument, "已上传文档：{0}", "已上傳文件：{0}", "Uploaded document: {0}", "传好啦：{0}", "已上传文档：{0}")
        put(StringKey.ChatPaperOpened, "已打开 PDF，可在“阅读”标签继续助读", "已開啟 PDF，可在「閱讀」標籤繼續助讀", "PDF opened. Continue reading in the Reading tab.", "PDF 打开啦，去“阅读”继续看喵", "已打开 PDF，可在“阅读”标签继续助读")
        put(StringKey.ChatUploadFailed, "上传失败，请重试", "上傳失敗，請重試", "Upload failed. Try again.", "没传上去，再试一次喵", "上传失败，请重试")
        put(StringKey.ChatVoiceStart, "语音输入", "語音輸入", "Voice input", "说给我听", "语音输入")
        put(StringKey.ChatVoiceStop, "停止听写", "停止聽寫", "Stop listening", "听好啦", "停止听写")
        put(StringKey.ChatVoiceUnavailable, "此设备暂不支持语音输入", "此裝置暫不支援語音輸入", "Voice input is unavailable on this device", "这台设备还听不了喵", "此设备不支持语音输入")
        put(StringKey.ImageEditHint, "描述你想调整的地方", "描述你想調整的地方", "Describe what to change", "想怎么改呢", "描述调整内容")
        put(StringKey.ImageEditAction, "继续调整", "繼續調整", "Edit image", "继续改图", "继续调整")
        put(StringKey.ImageOriginal, "原图", "原圖", "Original", "原图", "原图")
        put(StringKey.ImageUpdated, "新图", "新圖", "Updated", "新图", "新图")
        put(StringKey.ImagePrompt, "提示词：{0}", "提示詞：{0}", "Prompt: {0}", "提示词：{0}", "提示词：{0}")
        put(StringKey.ImageSaveToGallery, "保存到相册", "儲存到相簿", "Save to gallery", "存到相册喵", "保存到相册")
        put(StringKey.ChatAddSchedule, "添加到日程", "新增到日程", "Add to schedule", "加进日程喵", "添加到日程")
        put(StringKey.RouteCalendarRequest, "把刚规划好的路线添加到日程", "把剛規劃好的路線新增到日程", "Add the route I just planned to my calendar", "把刚规划好的路线加进日程喵", "把刚规划好的路线添加到日程")
        put(StringKey.HintFreshness, "回答基于近期公开信息", "回答基於近期公開資訊", "Based on recent public information", "这是最近的信息整理喵", "回答基于近期公开信息")
        put(StringKey.HintFreshnessLogin, "登录后可获取更新的信息", "登入後可取得更新的資訊", "Sign in for fresher information", "登录后信息会更新鲜喵", "登录后可获取更新的信息")
        put(StringKey.HintSkill, "已使用技能：{0}", "已使用技能：{0}", "Skills used: {0}", "用到了：{0}", "已使用技能：{0}")
        put(StringKey.HintSkillLogin, "登录后可解锁更多技能：{0}", "登入後可解鎖更多技能：{0}", "Sign in for more skills: {0}", "登录后能解锁：{0}", "登录后可解锁更多技能：{0}")
        put(StringKey.ChatRestoreFailed, "对话恢复失败，请重试", "對話恢復失敗，請重試", "Couldn't restore this chat. Try again.", "没找回这段对话，再试一次喵", "对话恢复失败，请重试")
        put(StringKey.ChatConnectionInterrupted, "连接中断，请重试", "連線中斷，請重試", "Connection interrupted. Try again.", "连接断了一下，再试试喵", "连接中断，请重试")
        put(StringKey.ChatGenerationFailed, "生成失败，请重试", "生成失敗，請重試", "Generation failed. Try again.", "这次没写完，再试一次喵", "生成失败，请重试")
        put(StringKey.ChatImageFailed, "图片处理失败，请重试", "圖片處理失敗，請重試", "Image edit failed. Try again.", "图片没改好，再试一次喵", "图片处理失败，请重试")
        put(StringKey.OperationFailed, "操作失败，请稍后重试", "操作失敗，請稍後重試", "Something went wrong. Try again.", "这次没办好，稍后再试喵", "操作失败，请重试")
        put(StringKey.NetworkUnavailable, "网络暂时不可用，请稍后重试", "網路暫時無法使用，請稍後重試", "You're offline. Try again when connected.", "网络开小差了，稍后再试喵", "网络不可用，请稍后重试")
        put(StringKey.SessionExpired, "登录已过期，请重新登录", "登入已過期，請重新登入", "Your session expired. Sign in again.", "登录过期了，再登录一次喵", "登录已过期，请重新登录")
        put(StringKey.LoginRequired, "登录后即可使用此功能", "登入後即可使用此功能", "Sign in to use this feature.", "登录后就能用啦喵", "请先登录")
        put(StringKey.MembershipRequired, "当前方案暂不支持此功能", "目前方案暫不支援此功能", "This feature isn't included in your current plan.", "当前方案还用不了这个功能喵", "当前方案不支持此功能")
        put(StringKey.TooManyRequests, "操作有点频繁，请稍后再试", "操作有點頻繁，請稍後再試", "Too many requests. Try again shortly.", "操作太快啦，稍后再试喵", "请求频繁，请稍后重试")
        put(StringKey.ServiceUnavailable, "服务暂时不可用，请稍后重试", "服務暫時無法使用，請稍後重試", "The service is temporarily unavailable. Try again later.", "服务在休息一下，稍后再试喵", "服务暂不可用，请稍后重试")

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
        put(StringKey.SkillsComponentApiHint, "用这些接口把 Skill 的结果安全展示在 Floris 中。底层能力由平台自动处理。", "用這些介面把 Skill 的結果安全顯示在 Floris 中。底層能力由平台自動處理。", "Use these actions to render Skill results in Floris. The platform handles the underlying services.", "用这些接口把 Skill 结果展示出来，底层交给 Floris 喵。", "用于展示 Skill 结果；底层能力由平台处理。")
        put(StringKey.SkillsComponentApiVersion, "版本 {0} · {1} 个接口", "版本 {0} · {1} 個介面", "Version {0} · {1} actions", "版本 {0} · {1} 个接口喵", "版本 {0} · {1} 个接口")
        put(StringKey.SkillsComponentApiParameters, "参数", "參數", "Parameters", "参数", "参数")
        put(StringKey.SkillsComponentApiExample, "调用示例", "呼叫範例", "Example", "调用例子", "调用示例")
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
        put(StringKey.CalendarAdd, "添加日程", "新增日程", "Add event", "添加日程喵", "添加日程")
        put(StringKey.CalendarEdit, "编辑", "編輯", "Edit", "改一下", "编辑")
        put(StringKey.CalendarDelete, "删除", "刪除", "Delete", "删掉", "删除")
        put(StringKey.CalendarEventTitle, "日程名称", "日程名稱", "Title", "要做什么", "日程名称")
        put(StringKey.CalendarLocation, "地点（可选）", "地點（可選）", "Location (optional)", "在哪里呀", "地点（可选）")
        put(StringKey.CalendarStart, "开始时间", "開始時間", "Start time", "什么时候开始", "开始时间")
        put(StringKey.CalendarDuration, "时长（分钟）", "時長（分鐘）", "Duration (minutes)", "要多久", "时长（分钟）")
        put(StringKey.CalendarSave, "保存日程", "儲存日程", "Save event", "收好日程", "保存日程")
        put(StringKey.CalendarYearMonth, "{0}年{1}月", "{0}年{1}月", "{1}/{0}", "{0}年{1}月", "{0}年{1}月")
        put(StringKey.CalendarPreviousMonth, "上月", "上月", "Previous month", "上个月", "上月")
        put(StringKey.CalendarNextMonth, "下月", "下月", "Next month", "下个月", "下月")
        put(StringKey.CalendarOnline, "线上", "線上", "Online", "线上", "线上")
        put(StringKey.CalendarLoadFailed, "日程加载失败", "日程載入失敗", "Couldn't load calendar", "日程没加载出来喵", "日程加载失败")
        put(StringKey.CalendarSaveFailed, "日程保存失败", "日程儲存失敗", "Couldn't save the event", "日程没存上喵", "日程保存失败")
        put(StringKey.CalendarDeleteFailed, "日程删除失败", "日程刪除失敗", "Couldn't delete the event", "日程没删掉喵", "日程删除失败")
        put(StringKey.WeekMonday, "一", "一", "Mon", "一", "一")
        put(StringKey.WeekTuesday, "二", "二", "Tue", "二", "二")
        put(StringKey.WeekWednesday, "三", "三", "Wed", "三", "三")
        put(StringKey.WeekThursday, "四", "四", "Thu", "四", "四")
        put(StringKey.WeekFriday, "五", "五", "Fri", "五", "五")
        put(StringKey.WeekSaturday, "六", "六", "Sat", "六", "六")
        put(StringKey.WeekSunday, "日", "日", "Sun", "日", "日")
        put(StringKey.SkillsAdd, "添加 Skill", "新增 Skill", "Add Skill", "添加 Skill 喵", "添加 Skill")
        put(StringKey.SkillsImportTitle, "添加自己的 Skill", "新增自己的 Skill", "Add your Skill", "添加自己的 Skill 喵", "添加自己的 Skill")
        put(StringKey.SkillsImportUrl, "仓库或文档地址", "儲存庫或文件地址", "Repository or document URL", "仓库或文档地址", "仓库或文档地址")
        put(StringKey.SkillsImportName, "名称", "名稱", "Name", "叫什么名字", "名称")
        put(StringKey.SkillsImportDescription, "简介（可选）", "簡介（可選）", "Description (optional)", "简单介绍一下", "简介（可选）")
        put(StringKey.SkillsImportInstructions, "使用说明", "使用說明", "Instructions", "告诉 Floris 怎么做", "使用说明")
        put(StringKey.SkillsImport, "导入", "匯入", "Import", "导入喵", "导入")
        put(StringKey.SkillsChooseFile, "选择 MD、JSON 或 ZIP", "選擇 MD、JSON 或 ZIP", "Choose MD, JSON, or ZIP", "选个文件喵", "选择 MD、JSON 或 ZIP")
        put(StringKey.SkillsPrivate, "我的 Skills", "我的 Skills", "My Skills", "我的 Skills", "我的 Skills")
        put(StringKey.SkillsRemove, "移除", "移除", "Remove", "移除", "移除")
        put(StringKey.SkillsUploads, "私有 Skill 包", "私有 Skill 套件", "Private Skill packages", "私有 Skill 包", "私有 Skill 包")
        put(StringKey.SkillsSubmitReview, "提交广场审核", "提交廣場審核", "Submit for review", "提交到广场看看", "提交广场审核")
        put(StringKey.SkillsPendingReview, "审核中", "審核中", "In review", "正在审核", "审核中")
        put(StringKey.SkillsApproved, "已通过", "已通過", "Approved", "审核通过", "已通过")
        put(StringKey.SkillsRejected, "未通过", "未通過", "Rejected", "没有通过", "未通过")
        put(StringKey.SkillsStored, "仅自己可见", "僅自己可見", "Private", "只给自己看", "仅自己可见")
        put(StringKey.SkillsConnection, "连接服务", "連接服務", "Connect service", "接上服务", "连接服务")
        put(StringKey.SkillsConnectionToken, "粘贴访问令牌", "貼上存取權杖", "Paste access token", "把访问令牌放这里", "输入访问令牌")
        put(StringKey.SkillsConnect, "安全连接", "安全連接", "Connect", "连上它", "连接")
        put(StringKey.SkillsConnected, "已连接", "已連接", "Connected", "已经连好啦", "已连接")
        put(StringKey.SkillsDisconnect, "断开", "中斷連線", "Disconnect", "先断开", "断开")
        put(StringKey.SkillsMarketFailed, "Skills 加载失败", "Skills 載入失敗", "Couldn't load Skills", "Skills 没加载出来喵", "Skills 加载失败")
        put(StringKey.SkillsEmptyTitle, "暂无 Skills", "暫無 Skills", "No Skills yet", "这里还空着喵", "暂无 Skills")
        put(StringKey.SkillsEmptyBody, "Skills 广场暂时为空", "Skills 廣場暫時為空", "The marketplace is empty for now", "广场里暂时没有新本领", "Skills 广场暂时为空")
        put(StringKey.SkillsOperationFailed, "操作失败，请重试", "操作失敗，請重試", "Couldn't complete that. Try again.", "这次没办好，再试一次喵", "操作失败，请重试")
        put(StringKey.SkillsImportFailed, "导入失败，请检查内容", "匯入失敗，請檢查內容", "Import failed. Check the content.", "没能装进去，检查一下内容喵", "导入失败，请检查内容")
        put(StringKey.SkillsSubmitFailed, "提交失败，请重试", "提交失敗，請重試", "Submission failed. Try again.", "没递上去，再试一次喵", "提交失败，请重试")
        put(StringKey.SkillsConnectFailed, "连接失败，请重试", "連接失敗，請重試", "Connection failed. Try again.", "没连上，再试一次喵", "连接失败，请重试")
        put(StringKey.SkillsDisconnectFailed, "断开失败，请重试", "中斷連線失敗，請重試", "Couldn't disconnect. Try again.", "没断开，再试一次喵", "断开失败，请重试")
        put(StringKey.SkillsOfficial, "Floris 官方", "Floris 官方", "Floris", "Floris 官方", "Floris 官方")
        put(StringKey.SkillsConflicts, "不兼容：{0}", "不相容：{0}", "Conflicts: {0}", "不能和这些一起用：{0}", "不兼容：{0}")
        put(StringKey.SkillsRecommends, "推荐搭配：{0}", "推薦搭配：{0}", "Works well with: {0}", "推荐一起开：{0}", "推荐搭配：{0}")
        put(StringKey.SkillCategoryFoundation, "基础能力", "基礎能力", "Essentials", "基础能力", "基础能力")
        put(StringKey.SkillCategoryKnowledge, "知识检索", "知識檢索", "Knowledge", "知识检索", "知识检索")
        put(StringKey.SkillCategoryCreative, "创作", "創作", "Creative", "创作", "创作")
        put(StringKey.SkillCategoryProductivity, "效率", "效率", "Productivity", "效率", "效率")
        put(StringKey.SkillCategoryLocation, "位置服务", "位置服務", "Location", "位置服务", "位置服务")
        put(StringKey.SkillCategoryOther, "其他", "其他", "Other", "其他", "其他")
        put(StringKey.ReadingUpload, "上传 PDF", "上傳 PDF", "Upload PDF", "上传 PDF 喵", "上传 PDF")
        put(StringKey.ReadingUploading, "上传中…", "上傳中…", "Uploading…", "正在上传喵…", "上传中…")
        put(StringKey.ReadingSave, "保存", "儲存", "Save", "收好", "保存")
        put(StringKey.ReadingSaved, "已保存", "已儲存", "Saved", "收好啦", "已保存")
        put(StringKey.ReadingDelete, "删除", "刪除", "Delete", "删掉", "删除")
        put(StringKey.ReadingUploadFailed, "上传失败，请重试", "上傳失敗，請重試", "Upload failed. Try again", "上传失败了喵", "上传失败，请重试")
        put(StringKey.ReadingResults, "检索结果 · {0}", "檢索結果 · {0}", "Results · {0}", "找到 {0} 篇喵", "检索结果 · {0}")
        put(StringKey.ReadingAutoOrganize, "自动整理", "自動整理", "Auto-organize", "自动整理", "自动整理")
        put(StringKey.ReadingFolderNew, "新建文件夹", "新增資料夾", "New folder", "新建文件夹", "新建文件夹")
        put(StringKey.ReadingFolderRename, "重命名文件夹", "重新命名資料夾", "Rename folder", "给文件夹换名", "重命名文件夹")
        put(StringKey.ReadingFolderDelete, "删除文件夹", "刪除資料夾", "Delete folder", "删除文件夹", "删除文件夹")
        put(StringKey.ReadingAll, "全部", "全部", "All", "全部", "全部")
        put(StringKey.ReadingPaper, "论文", "論文", "Paper", "论文", "论文")
        put(StringKey.ReadingOpen, "打开", "開啟", "Open", "打开看看", "打开")
        put(StringKey.ReadingOpening, "打开中…", "開啟中…", "Opening…", "正在打开…", "打开中…")
        put(StringKey.ReadingMove, "移动", "移動", "Move", "挪到…", "移动")
        put(StringKey.ReadingAnalyze, "分析", "分析", "Analyze", "仔细分析", "分析")
        put(StringKey.ReadingAsk, "提问", "提問", "Ask", "问问论文", "提问")
        put(StringKey.ReadingAskHint, "你想问这份文档什么？", "你想問這份文件什麼？", "What would you like to ask?", "想问这份文档什么喵？", "输入问题")
        put(StringKey.ReadingSaveResult, "保存结果", "儲存結果", "Save result", "把结果收好", "保存结果")
        put(StringKey.ReadingSearchFailed, "论文检索失败", "論文檢索失敗", "Paper search failed", "论文没找到喵", "论文检索失败")
        put(StringKey.ReadingSaveFailed, "保存失败，请重试", "儲存失敗，請重試", "Couldn't save. Try again.", "没存上，再试一次喵", "保存失败，请重试")
        put(StringKey.ReadingDeleteFailed, "删除失败，请重试", "刪除失敗，請重試", "Couldn't delete. Try again.", "没删掉，再试一次喵", "删除失败，请重试")
        put(StringKey.ReadingOperationFailed, "操作失败，请重试", "操作失敗，請重試", "Couldn't complete that. Try again.", "这次没办好喵", "操作失败，请重试")
        put(StringKey.ReadingOpenFailed, "文件打开失败", "檔案開啟失敗", "Couldn't open the file", "文件没打开喵", "文件打开失败")
        put(StringKey.ReadingRunFailed, "阅读失败，请重试", "閱讀失敗，請重試", "Reading failed. Try again.", "这次没读好喵", "阅读失败，请重试")
        put(StringKey.ReadingUntitledDocument, "未命名文档", "未命名文件", "Untitled document", "还没起名的文档", "未命名文档")
        put(StringKey.ReadingUntitledFolder, "未命名文件夹", "未命名資料夾", "Untitled folder", "还没起名的文件夹", "未命名文件夹")

        // ---- 地图 ----
        put(StringKey.MapTitle, "地图", "地圖", "Map", "地图", "地图")
        put(StringKey.MapNamedRoute, "{0}路线", "{0}路線", "{0} route", "{0}路线", "{0}路线")
        put(StringKey.DurationHoursMinutes, "{0} 小时 {1} 分", "{0} 小時 {1} 分", "{0} hr {1} min", "{0} 小时 {1} 分", "{0} 小时 {1} 分")
        put(StringKey.DurationMinutes, "{0} 分钟", "{0} 分鐘", "{0} min", "{0} 分钟", "{0} 分钟")
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
        put(StringKey.MapSearchFailed, "地点搜索失败", "地點搜尋失敗", "Place search failed", "没找到地点喵", "地点搜索失败")
        put(StringKey.MapNeedTwoPlaces, "至少选择两个地点", "至少選擇兩個地點", "Choose at least two places", "至少选两个地方喵", "至少选择两个地点")
        put(StringKey.MapServiceUnavailable, "路线服务暂不可用", "路線服務暫不可用", "Routes are temporarily unavailable", "路线暂时没回来喵", "路线服务暂不可用")
        put(StringKey.MapPlanFailed, "路线规划失败", "路線規劃失敗", "Route planning failed", "路线没规划好喵", "路线规划失败")

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
        put(StringKey.ProfileDefaultUser, "Floris 用户", "Floris 使用者", "Floris user", "Floris 的朋友", "Floris 用户")
        put(StringKey.ProfileReadingDesc, "论文、文档与自动整理的文件夹", "論文、文件與自動整理的資料夾", "Papers, documents and organized folders", "论文和文档都收在这里", "论文、文档与文件夹")
        put(StringKey.ProfileMapDesc, "地点、当前位置与路线结果", "地點、目前位置與路線結果", "Places, current location and routes", "地点和路线都在这里", "地点、位置与路线")
        put(StringKey.ProfileSettingsDesc, "主题、语言、偏好与用量", "主題、語言、偏好與用量", "Theme, language, preferences and usage", "样子和习惯都能调整", "主题、语言、偏好与用量")
        put(StringKey.ProfileAboutDesc, "查看功能说明与使用帮助", "查看功能說明與使用說明", "Feature guide and help", "看看我都会什么", "功能说明与帮助")
        put(StringKey.Important, "重要", "重要", "Important", "很重要", "重要")
        put(StringKey.MembershipPlus, "Plus 会员", "Plus 會員", "Plus", "Plus 会员", "Plus 会员")
        put(StringKey.MembershipPro, "Pro 会员", "Pro 會員", "Pro", "Pro 会员", "Pro 会员")
        put(StringKey.MembershipFree, "免费版", "免費版", "Free", "免费版", "免费版")
        put(StringKey.MembershipGuest, "游客", "訪客", "Guest", "游客", "游客")
        put(StringKey.ProfileAvatar, "头像", "頭像", "Avatar", "头像", "头像")
        put(StringKey.ProfileDefaultDisplayName, "Floris 用户", "Floris 使用者", "Floris user", "Floris 的朋友", "Floris 用户")
        put(StringKey.ProfileNameUpdated, "昵称已更新", "暱稱已更新", "Name updated", "新名字记好啦喵", "昵称已更新")
        put(StringKey.ProfileUpdateFailed, "更新失败，请重试", "更新失敗，請重試", "Update failed. Try again.", "没更新好，再试一次喵", "更新失败，请重试")
        put(StringKey.ProfileAvatarUpdated, "头像已更新", "頭像已更新", "Avatar updated", "新头像换好啦喵", "头像已更新")
        put(StringKey.ProfileAvatarUpdateFailed, "头像更新失败，请重试", "頭像更新失敗，請重試", "Avatar update failed. Try again.", "头像没换好喵", "头像更新失败，请重试")
        put(StringKey.HistoryLoadFailed, "对话加载失败", "對話載入失敗", "Couldn't load conversations", "对话没加载出来喵", "对话加载失败")

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
        put(StringKey.SettingsParallelImages, "边搜边找图", "邊搜邊找圖", "Search images in parallel", "边搜边找图喵", "并行图片搜索")
        put(StringKey.SettingsParallelImagesDesc, "让图片审核与正文检索同时进行", "讓圖片審核與正文檢索同時進行", "Review images while retrieving sources", "图片和资料一起找喵", "图片审核与检索并行")
        put(StringKey.SettingsMapExperience, "地图与路线", "地圖與路線", "Maps and routes", "地图和路线", "地图与路线")
        put(StringKey.SettingsMapExperienceDesc, "这些设置会影响下一次地点搜索和路线规划", "這些設定會影響下一次地點搜尋和路線規劃", "Applied to your next place search and route", "下次规划就会按这里来喵", "影响后续地点与路线结果")
        put(StringKey.SettingsMapServiceMode, "规划细致度", "規劃細緻度", "Planning detail", "规划细致度", "规划细致度")
        put(StringKey.SettingsMapFast, "快速", "快速", "Fast", "快一点", "快速")
        put(StringKey.SettingsMapBalanced, "均衡", "均衡", "Balanced", "刚刚好", "均衡")
        put(StringKey.SettingsMapComplete, "完整", "完整", "Complete", "细细规划", "完整")
        put(StringKey.SettingsMapPlaceCount, "地点结果", "地點結果", "Place results", "地点结果", "地点结果")
        put(StringKey.SettingsMapRouteStops, "单条路线地点", "單條路線地點", "Stops per route", "路线地点数", "单条路线地点")
        put(StringKey.SettingsMapTimeout, "搜索等待（秒）", "搜尋等待（秒）", "Search timeout (sec)", "最多等几秒", "搜索等待（秒）")
        put(StringKey.SettingsPreferredRoute, "常用出行方式", "常用出行方式", "Preferred travel mode", "平时怎么走", "常用出行方式")
        put(StringKey.SettingsRouteStrategy, "路线优先级", "路線優先級", "Route priority", "路线先看什么", "路线优先级")
        put(StringKey.SettingsNearTolerance, "近似路线容差（分钟）", "近似路線容差（分鐘）", "Near-route tolerance (min)", "可多花几分钟", "近似路线容差（分钟）")
        put(StringKey.SettingsLearnRoute, "记住路线偏好", "記住路線偏好", "Learn route preferences", "记住我的路线习惯", "记住路线偏好")
        put(StringKey.RouteDriving, "驾车", "駕車", "Drive", "驾车", "驾车")
        put(StringKey.RouteTransit, "公交", "大眾運輸", "Transit", "公共交通", "公交")
        put(StringKey.RouteWalking, "步行", "步行", "Walk", "走路", "步行")
        put(StringKey.RouteBicycling, "骑行", "騎行", "Bike", "骑车", "骑行")
        put(StringKey.RouteBus, "公交", "公車", "Bus", "坐公交", "公交")
        put(StringKey.RouteSubway, "地铁", "捷運", "Metro", "坐地铁", "地铁")
        put(StringKey.RouteRail, "火车", "火車", "Rail", "坐火车", "火车")
        put(StringKey.StrategyTimeCost, "时间兼顾费用", "時間兼顧費用", "Time, then cost", "先省时间再省钱", "时间兼顾费用")
        put(StringKey.StrategyLeastTime, "最快", "最快", "Fastest", "最快到达", "最快")
        put(StringKey.StrategyLeastCost, "最省", "最省", "Lowest cost", "最省钱", "最省")
        put(StringKey.SettingsPersonalization, "个性化", "個人化", "Personalization", "更懂你", "个性化")
        put(StringKey.SettingsPersonalizationDesc, "管理记忆、主动提醒与长期计划", "管理記憶、主動提醒與長期計畫", "Manage memory, proactive notes and long-running plans", "看看我记住了什么喵", "管理记忆、提醒与长期计划")
        put(StringKey.PersonalizationTitle, "个性化", "個人化", "Personalization", "更懂你", "个性化")
        put(StringKey.MemorySection, "记忆", "記憶", "Memory", "我记住的", "记忆")
        put(StringKey.MemoryEnabled, "使用记忆", "使用記憶", "Use memory", "记住有用的小事", "使用记忆")
        put(StringKey.MemoryEnabledDesc, "让回答逐渐贴近你的偏好；新增记忆仍由你确认", "讓回答逐漸貼近你的偏好；新增記憶仍由你確認", "Personalize answers; new memories still need your approval", "想记住新东西前会先问你喵", "个性化回答；新增记忆需确认")
        put(StringKey.MemoryPending, "待你确认", "待你確認", "Needs your approval", "等你点头", "待确认")
        put(StringKey.MemorySaved, "已经记住", "已經記住", "Remembered", "已经记住啦", "已记住")
        put(StringKey.MemoryEmpty, "还没有记住任何偏好", "還沒有記住任何偏好", "No saved preferences yet", "还没记住东西喵", "暂无记忆")
        put(StringKey.MemoryReason, "为什么建议记住", "為什麼建議記住", "Why this was suggested", "为什么想记住", "建议理由")
        put(StringKey.MemoryReject, "不记住", "不記住", "Don't remember", "不要记", "拒绝")
        put(StringKey.MemoryRollback, "恢复上次", "恢復上次", "Restore previous", "换回上次", "恢复上一版")
        put(StringKey.MemoryClear, "清空记忆", "清空記憶", "Clear memory", "全部忘掉", "清空记忆")
        put(StringKey.MemoryClearTitle, "清空全部记忆？", "清空全部記憶？", "Clear all memory?", "要全部忘掉吗？", "清空全部记忆？")
        put(StringKey.MemoryClearBody, "只清除个性化记忆，不影响账号、聊天和文件。", "只清除個人化記憶，不影響帳號、聊天和檔案。", "This only clears personalized memory. Chats and files stay unchanged.", "只忘掉小习惯，聊天和文件都还在喵", "仅清除个性化记忆，不影响其他数据。")
        put(StringKey.RulesSection, "提醒建议", "提醒建議", "Reminder suggestions", "提醒小建议", "提醒建议")
        put(StringKey.ProactiveSection, "主动提醒", "主動提醒", "Proactive notes", "主动小话", "主动提醒")
        put(StringKey.ProactiveAutonomy, "处理方式", "處理方式", "Action mode", "怎么帮你", "处理方式")
        put(StringKey.ProactiveObserve, "仅观察", "僅觀察", "Observe", "先看看", "仅观察")
        put(StringKey.ProactiveRemind, "提醒", "提醒", "Remind", "提醒我", "提醒")
        put(StringKey.ProactivePropose, "先询问", "先詢問", "Ask first", "先问我", "先询问")
        put(StringKey.ProactiveLowRiskAuto, "低风险自动", "低風險自動", "Auto low-risk", "小事自动做", "低风险自动")
        put(StringKey.ProactiveQuietHours, "免打扰时段", "勿擾時段", "Quiet hours", "睡觉时别叫我", "免打扰时段")
        put(StringKey.ProactiveDailyLimit, "每天最多提醒", "每天最多提醒", "Daily limit", "每天最多说几次", "每日上限")
        put(StringKey.ProactiveLookahead, "提前关注（小时）", "提前關注（小時）", "Look ahead (hours)", "提前看几小时", "提前关注（小时）")
        put(StringKey.ProactiveWindowLimit, "单次展示数量", "單次顯示數量", "Items shown", "一次说几条", "单次展示数量")
        put(StringKey.ProactiveProviderLimit, "日程检查数量", "日程檢查數量", "Schedules checked", "一次看几个日程", "日程检查数量")
        put(StringKey.ProactiveRouteGap, "路线关注间隔（小时）", "路線關注間隔（小時）", "Route look-ahead gap (hours)", "隔几小时看路线", "路线间隔（小时）")
        put(StringKey.ProactiveTravelBuffer, "出行预留（分钟）", "出行預留（分鐘）", "Travel buffer (minutes)", "出门多留几分钟", "出行预留（分钟）")
        put(StringKey.WorkflowSection, "长期计划", "長期計畫", "Long-running plans", "一步步计划", "长期计划")
        put(StringKey.WorkflowEmpty, "暂无进行中的计划", "暫無進行中的計畫", "No active plans", "现在没有长期计划喵", "暂无计划")
        put(StringKey.WorkflowConfirm, "开始计划", "開始計畫", "Start plan", "开始吧", "开始计划")
        put(StringKey.WorkflowReject, "暂不开始", "暫不開始", "Not now", "先不要", "拒绝计划")
        put(StringKey.WorkflowCancel, "结束计划", "結束計畫", "End plan", "结束吧", "结束计划")
        put(StringKey.WorkflowCompleteStep, "完成这一步", "完成這一步", "Complete step", "这步做好啦", "完成步骤")
        put(StringKey.WorkflowSkipStep, "跳过", "跳過", "Skip", "先跳过", "跳过")
        put(StringKey.WorkflowMarkFailed, "遇到问题", "遇到問題", "Report a problem", "这步卡住了", "标记失败")
        put(StringKey.WorkflowCompensationComplete, "已处理影响", "已處理影響", "Impact resolved", "影响处理好啦", "补偿完成")
        put(StringKey.SettingsSaved, "已保存", "已儲存", "Saved", "记好啦", "已保存")
        put(StringKey.SettingsSaveFailed, "保存失败，请重试", "儲存失敗，請重試", "Couldn't save. Try again.", "没记住，再试一次喵", "保存失败，请重试")
        put(StringKey.SettingsResetSucceeded, "数据已清除", "資料已清除", "Data cleared", "已经收拾干净啦", "数据已清除")
        put(StringKey.SettingsResetFailed, "清除失败，请重试", "清除失敗，請重試", "Couldn't clear data. Try again.", "没清干净，再试一次喵", "清除失败，请重试")
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
            "将删除全部会话、工作区与文件，且无法恢复。账号与个人信息会保留。",
            "將刪除全部對話、工作區與檔案，且無法復原。帳號與個人資訊會保留。",
            "This deletes all conversations, workspaces and files. Your account and profile are kept.",
            "纸页和小东西都会不见，捡不回来的喵…不过名字还留着",
            "将删除全部会话、工作区与文件。账号与个人信息保留。",
        )
        put(StringKey.SettingsResetConfirm, "确认清除", "確認清除", "Erase", "确认收拾", "确认清除")
        put(StringKey.SettingsResetting, "清除中…", "清除中…", "Clearing…", "正在清理喵…", "清除中…")
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
        put(StringKey.LoginInvalidEmail, "请输入有效的邮箱地址", "請輸入有效的電子郵件地址", "Enter a valid email address", "这个邮箱好像不对喵", "请输入有效邮箱")
        put(StringKey.LoginEnterCode, "请输入邮箱收到的验证码", "請輸入電子郵件收到的驗證碼", "Enter the code from your email", "把邮箱里的验证码填进来喵", "请输入验证码")
        put(StringKey.LoginOperationFailed, "登录失败，请重试", "登入失敗，請重試", "Sign-in failed. Try again.", "没能登录，再试一次喵", "登录失败，请重试")

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

    fun format(key: StringKey, language: Language, vararg args: Any): String =
        args.foldIndexed(of(key, language)) { index, text, value ->
            text.replace("{$index}", value.toString())
        }

    internal fun hasCompleteEntry(key: StringKey): Boolean =
        catalog[key]?.let { entry ->
            entry.size == Language.entries.size && entry.all(String::isNotBlank)
        } == true
}

class StringResolver(private val language: () -> Language) {
    fun get(key: StringKey, vararg args: Any): String = Strings.format(key, language(), *args)
}
