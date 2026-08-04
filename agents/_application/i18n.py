"""Backend localization for user-visible copy and model-facing instructions.

Frontend text lives in ``frontend/src/i18n.tsx``.  Backend code must use this
catalog for fixed text that can reach a user or an LLM.  Keeping both kinds of
copy behind stable keys prevents orchestration code from silently becoming a
second, Chinese-only presentation layer.
"""

from __future__ import annotations

from typing import Final

from agents._application.i18n_catalogs import MODEL_CATALOG


SUPPORTED_LANGUAGES: Final = ("zh-CN", "zh-TW", "en", "cat-cute", "cat-cold")
_LANGUAGE_INDEX: Final = {
    language: index for index, language in enumerate(SUPPORTED_LANGUAGES)
}

LocalizedEntry = tuple[str, str, str, str, str]


# Every fixed user-visible entry provides all product languages.  Model-only
# policy uses the same catalog as well; it may intentionally share wording
# across cat variants because the separate language instruction owns tone.
CATALOG: Final[dict[str, LocalizedEntry]] = {
    "chat.message_required": (
        "缺少消息内容。",
        "缺少訊息內容。",
        "A message is required.",
        "还没有消息内容喵。",
        "缺少消息内容。",
    ),
    "chat.request_failed": (
        "请求失败",
        "請求失敗",
        "Request failed",
        "请求失败了喵",
        "请求失败",
    ),
    "chat.previous_run_timed_out": (
        "上一次运行已超时，请重新发送",
        "上一次執行已逾時，請重新傳送",
        "The previous run timed out. Please send your message again.",
        "上一次运行超时了，请重新发送喵",
        "上一次运行已超时，请重新发送。",
    ),
    "chat.conversation_busy": (
        "该对话仍在处理中；刷新后会自动恢复，请稍候或先停止当前运行",
        "此對話仍在處理中；重新整理後會自動恢復，請稍候或先停止目前執行",
        "This conversation is still processing. It will recover after refresh; please wait or stop the current run.",
        "这段对话还在处理中，刷新后会自动恢复；请稍等或先停下当前运行喵",
        "该对话仍在处理中。刷新后会自动恢复；请稍候或先停止当前运行。",
    ),
    "chat.manual_location_answer": (
        "你刚填写的位置是：{location}。这是你手动提供的大致位置，不是浏览器实时定位；我可以据此继续做附近推荐、路线规划或日程安排。",
        "你剛填寫的位置是：{location}。這是你手動提供的大致位置，不是瀏覽器即時定位；我可以據此繼續做附近推薦、路線規劃或行程安排。",
        "You entered this approximate location: {location}. It was provided manually rather than detected live by the browser; I can use it for nearby recommendations, routes, or schedules.",
        "你刚填写的位置是：{location}。这是手动提供的大致位置，不是浏览器实时定位；我可以接着做附近推荐、路线规划或日程安排喵。",
        "你填写的位置是：{location}。这是手动提供的大致位置，并非浏览器实时定位；可继续用于附近推荐、路线规划或日程安排。",
    ),
    "chat.location_context.available": (
        "已授权且新鲜，可作为路线隐式起点或附近搜索参照（精确坐标仅供地图工具使用）",
        "已授權且仍在有效時間內，可作為路線隱含起點或附近搜尋參照（精確座標僅供地圖工具使用）",
        "Authorized and fresh; it may be used as an implicit route origin or nearby-search anchor (exact coordinates are restricted to map tools).",
        "定位已授权且仍然新鲜，可作为路线起点或附近搜索参照；精确坐标只交给地图工具喵",
        "定位已授权且仍然有效，可作为路线起点或附近搜索参照；精确坐标仅供地图工具使用。",
    ),
    "chat.location_context.unavailable": (
        "不可用（浏览器本轮结果：{request_state}）；不得声称已定位",
        "不可用（瀏覽器本輪結果：{request_state}）；不得聲稱已定位",
        "Unavailable (browser result for this turn: {request_state}); do not claim that a location was obtained.",
        "定位不可用（浏览器本轮结果：{request_state}）；不能说已经定位了喵",
        "定位不可用（浏览器本轮结果：{request_state}）；不得声称已定位。",
    ),
    "chat.language_instruction.zh-CN": (
        "使用自然、清晰的简体中文，保留 Markdown 结构与链接。",
        "使用自然、清晰的簡體中文，保留 Markdown 結構與連結。",
        "Use clear, natural Simplified Chinese and preserve Markdown structure and links.",
        "使用自然、清晰的简体中文，保留 Markdown 结构与链接。",
        "使用自然、清晰的简体中文，保留 Markdown 结构与链接。",
    ),
    "chat.language_instruction.zh-TW": (
        "使用自然、清晰的繁体中文，保留 Markdown 结构与链接。",
        "使用自然、清晰的繁體中文，保留 Markdown 結構與連結。",
        "Use clear, natural Traditional Chinese and preserve Markdown structure and links.",
        "使用自然、清晰的繁体中文，保留 Markdown 结构与链接。",
        "使用自然、清晰的繁体中文，保留 Markdown 结构与链接。",
    ),
    "chat.language_instruction.en": (
        "使用清晰、自然的英文，除非用户明确要求其他语言。",
        "使用清晰、自然的英文，除非使用者明確要求其他語言。",
        "Respond in clear, natural English unless the user explicitly requests another language.",
        "使用清晰、自然的英文，除非用户明确要求其他语言。",
        "使用清晰、自然的英文，除非用户明确要求其他语言。",
    ),
    "chat.language_instruction.cat-cute": (
        "使用简体中文，像亲人的可爱橘猫一样适度加入“喵”，但保持准确清晰，不要过度卖萌。",
        "使用簡體中文，像親人的可愛橘貓一樣適度加入「喵」，但保持準確清晰，不要過度賣萌。",
        "Use Simplified Chinese with a warm, cute orange-cat voice and an occasional ‘meow’, while staying accurate and clear.",
        "使用简体中文，像亲人的可爱橘猫一样适度加入“喵”，但保持准确清晰，不要过度卖萌。",
        "使用简体中文，像亲人的可爱橘猫一样适度加入“喵”，但保持准确清晰，不要过度卖萌。",
    ),
    "chat.language_instruction.cat-cold": (
        "使用简体中文，像冷静克制的橘猫，偶尔使用简短的“喵”，不要撒娇，保持准确直接。",
        "使用簡體中文，像冷靜克制的橘貓，偶爾使用簡短的「喵」，不要撒嬌，保持準確直接。",
        "Use Simplified Chinese with a calm, restrained orange-cat voice and only an occasional brief ‘meow’; stay accurate and direct.",
        "使用简体中文，像冷静克制的橘猫，偶尔使用简短的“喵”，不要撒娇，保持准确直接。",
        "使用简体中文，像冷静克制的橘猫，偶尔使用简短的“喵”，不要撒娇，保持准确直接。",
    ),
    "chat.location.name": (
        "当前位置", "目前位置", "Current location", "当前位置喵", "当前位置",
    ),
    "chat.location.ephemeral_address": (
        "本次请求的浏览器定位（不写入长期记忆）",
        "本次請求的瀏覽器定位（不寫入長期記憶）",
        "Browser location for this request (not stored in long-term memory)",
        "本次请求的浏览器定位（不会写入长期记忆）喵",
        "本次请求的浏览器定位（不写入长期记忆）",
    ),
    "chat.empty_generation": (
        "模型未返回有效回答，请重试。",
        "模型未傳回有效回答，請重試。",
        "The model did not return a valid answer. Please try again.",
        "模型没有返回有效回答，请再试一次喵。",
        "模型未返回有效回答，请重试。",
    ),
    "chat.token_budget_reached": (
        "已达到今日 Token 预算；请在“记忆与学习”中调整预算或切换策略",
        "已達到今日 Token 預算；請在「記憶與學習」中調整預算或切換策略",
        "Today's token budget has been reached. Adjust the budget or strategy in Memory & Learning.",
        "今天的 Token 预算已经用完，请在“记忆与学习”里调整预算或策略喵",
        "已达到今日 Token 预算。请在“记忆与学习”中调整预算或策略。",
    ),
    "chat.run_interrupted": (
        "运行已中断，请重试",
        "執行已中斷，請重試",
        "The run was interrupted. Please try again.",
        "运行中断了，请重试喵",
        "运行已中断，请重试。",
    ),
    "chat.progress.search_ready": (
        "富搜索来源和媒体已准备",
        "豐富搜尋來源與媒體已準備",
        "Search sources and media are ready",
        "富搜索的来源和媒体准备好了喵",
        "富搜索来源和媒体已准备",
    ),
    "chat.progress.papers_ready": (
        "论文结果已准备",
        "論文結果已準備",
        "Paper results are ready",
        "论文结果准备好了喵",
        "论文结果已准备",
    ),
    "chat.clarification.required_title": (
        "请补充必要信息", "請補充必要資訊", "A little more information is needed", "请再补充一点必要信息喵", "请补充必要信息",
    ),
    "chat.clarification.required_prompt": (
        "缺少以下信息时无法继续处理。", "缺少以下資訊時無法繼續處理。", "The request cannot continue without the information below.", "还缺少下面的信息，补上后才能继续喵。", "缺少以下信息，当前无法继续。",
    ),
    "chat.location.field.nearby": (
        "你现在在哪里？", "你現在在哪裡？", "Where are you now?", "你现在在哪里呀？", "你现在在哪里？",
    ),
    "chat.location.field.route": (
        "从哪里出发？", "從哪裡出發？", "Where are you leaving from?", "从哪里出发呀？", "从哪里出发？",
    ),
    "chat.location.field.current": (
        "你目前所在的位置或出发地", "你目前所在的位置或出發地", "Your current location or starting point", "你现在的位置或出发地", "你目前所在的位置或出发地",
    ),
    "chat.location.placeholder": (
        "例如：北京市海淀区中关村，或吉林大学前卫南区",
        "例如：北京市海淀區中關村，或吉林大學前衛南區",
        "For example: Zhongguancun, Haidian District, Beijing",
        "例如：北京市海淀区中关村，或吉林大学前卫南区",
        "例如：北京市海淀区中关村，或吉林大学前卫南区",
    ),
    "chat.location.denied.title": (
        "定位权限未开启", "尚未開啟定位權限", "Location access is off", "定位权限还没打开喵", "定位权限未开启",
    ),
    "chat.location.denied.prompt": (
        "浏览器已拒绝本网站读取位置。你可以在当前网站的权限设置中改为允许后重试，也可以直接填写你所在的区域或附近地标，提交后我会继续处理。",
        "瀏覽器已拒絕本網站讀取位置。你可以在目前網站的權限設定中改為允許後重試，也可以直接填寫所在區域或附近地標，送出後我會繼續處理。",
        "The browser denied location access. Allow it in this site's permissions and retry, or enter your area or a nearby landmark so I can continue.",
        "浏览器拒绝了位置权限。可以在网站权限里允许后重试，也可以填写所在区域或附近地标，提交后我会继续处理喵。",
        "浏览器拒绝了位置权限。可在网站权限中允许后重试，或填写所在区域或附近地标后继续。",
    ),
    "chat.location.timeout.title": (
        "定位暂时超时", "定位暫時逾時", "Location timed out", "定位暂时超时了喵", "定位暂时超时",
    ),
    "chat.location.timeout.prompt": (
        "设备在 12 秒内没有返回位置，手机或平板上可确认系统定位服务已开启。你可以重新尝试，也可以直接填写{target}。",
        "裝置在 12 秒內沒有傳回位置，可確認手機或平板的系統定位服務已開啟。你可以重試，也可以直接填寫{target}。",
        "The device did not return a location within 12 seconds. Check that system location services are on, retry, or enter {target}.",
        "设备在 12 秒内没有返回位置，请确认系统定位服务已开启。可以重试，也可以填写{target}喵。",
        "设备在 12 秒内没有返回位置。请确认系统定位服务已开启，或填写{target}。",
    ),
    "chat.location.unavailable.title": (
        "设备暂时无法定位", "裝置暫時無法定位", "Location is unavailable", "设备暂时找不到位置喵", "设备暂时无法定位",
    ),
    "chat.location.unavailable.prompt": (
        "当前浏览器或设备没有提供可用位置。你可以换用支持定位的安全浏览器，也可以直接填写{target}。",
        "目前瀏覽器或裝置沒有提供可用位置。你可以改用支援定位的安全瀏覽器，也可以直接填寫{target}。",
        "This browser or device did not provide a usable location. Try a secure browser with location support, or enter {target}.",
        "当前浏览器或设备没有提供可用位置。可以换用支持定位的安全浏览器，也可以填写{target}喵。",
        "当前浏览器或设备没有提供可用位置。可换用支持定位的安全浏览器，或填写{target}。",
    ),
    "chat.location.target.nearby": (
        "附近搜索的起点", "附近搜尋的起點", "the starting point for the nearby search", "附近搜索的起点", "附近搜索的起点",
    ),
    "chat.location.target.origin": (
        "大致位置或出发地", "大致位置或出發地", "an approximate location or starting point", "大致位置或出发地", "大致位置或出发地",
    ),
    "chat.location.missing.nearby.title": (
        "需要附近搜索的起点", "需要附近搜尋的起點", "A nearby-search starting point is needed", "还需要附近搜索的起点喵", "需要附近搜索的起点",
    ),
    "chat.location.missing.route.title": (
        "需要路线起点", "需要路線起點", "A route origin is needed", "还需要路线起点喵", "需要路线起点",
    ),
    "chat.location.missing.current.title": (
        "需要你的位置", "需要你的位置", "Your location is needed", "还需要你的位置喵", "需要你的位置",
    ),
    "chat.location.missing.nearby.prompt": (
        "浏览器没有提供当前位置。请填写你所在的区域或附近地标，提交后我会自动继续查找，不需要重新描述需求。",
        "瀏覽器沒有提供目前位置。請填寫所在區域或附近地標，送出後我會自動繼續查找，不必重新描述需求。",
        "The browser did not provide your location. Enter your area or a nearby landmark and I will continue automatically.",
        "浏览器没有提供当前位置。填写所在区域或附近地标后，我会自动继续查找，不用重新描述喵。",
        "浏览器没有提供当前位置。填写所在区域或附近地标后会自动继续查找。",
    ),
    "chat.location.missing.route.prompt": (
        "浏览器没有提供当前位置。请填写路线起点，提交后我会自动继续规划。",
        "瀏覽器沒有提供目前位置。請填寫路線起點，送出後我會自動繼續規劃。",
        "The browser did not provide your location. Enter the route origin and I will continue planning automatically.",
        "浏览器没有提供当前位置。填写路线起点后，我会自动继续规划喵。",
        "浏览器没有提供当前位置。填写路线起点后会自动继续规划。",
    ),
    "chat.location.missing.current.prompt": (
        "浏览器没有提供当前位置。你可以填写大致位置，我会用它继续附近推荐、路线规划或日程安排。",
        "瀏覽器沒有提供目前位置。你可以填寫大致位置，我會用它繼續附近推薦、路線規劃或行程安排。",
        "The browser did not provide your location. Enter an approximate location to continue with nearby recommendations, routes, or schedules.",
        "浏览器没有提供当前位置。填写大致位置后，我会继续附近推荐、路线规划或日程安排喵。",
        "浏览器没有提供当前位置。可填写大致位置以继续附近推荐、路线规划或日程安排。",
    ),
    "model.chat.role.user": (
        "用户", "使用者", "User", "用户", "用户",
    ),
    "model.chat.recent_dialogue_header": (
        "[最近对话仅用于解析省略、代词、序号和对上一轮候选的选择。当前消息拥有最高优先级；必须把引用解析成候选的真实名称，不要把“第几个/那个/它”当作地点名称交给工具。]",
        "[最近對話僅用於解析省略、代詞、序號和對上一輪候選的選擇。目前訊息擁有最高優先級；必須把引用解析成候選的真實名稱，不要把「第幾個／那個／它」當作地點名稱交給工具。]",
        "[Use recent dialogue only to resolve omissions, pronouns, ordinals, and selections from prior candidates. The current message has highest priority. Resolve references to real candidate names; never pass phrases such as ‘the second one’, ‘that’, or ‘it’ to place tools as place names.]",
        "[最近对话仅用于解析省略、代词、序号和对上一轮候选的选择。当前消息优先；把引用还原成真实名称，不要把“第几个/那个/它”当作地点名称交给工具。]",
        "[最近对话仅用于解析省略、代词、序号和对上一轮候选的选择。当前消息优先；必须把引用解析成候选真实名称。]",
    ),
    "model.chat.current_message_header": (
        "[当前用户消息]", "[目前使用者訊息]", "[Current user message]", "[当前用户消息]", "[当前用户消息]",
    ),
    "model.chat.prior_answer": (
        "先前已提交的补充答案 {index}：{answer}",
        "先前已送出的補充答案 {index}：{answer}",
        "Previously submitted clarification answer {index}: {answer}",
        "先前已经提交的补充答案 {index}：{answer}",
        "先前已提交的补充答案 {index}：{answer}",
    ),
    "model.chat.clarification_continuation": (
        "[这是用户对上一轮结构化问题的补充答案，请结合原始目标规划尚未完成的能力；所有先前补充答案仍然有效，不要把答案误判为独立新问题或重复询问。]\n上一轮原始目标：{goal}\n{prior}本次补充答案：{current}",
        "[這是使用者對上一輪結構化問題的補充答案，請結合原始目標規劃尚未完成的能力；所有先前補充答案仍然有效，不要把答案誤判為獨立新問題或重複詢問。]\n上一輪原始目標：{goal}\n{prior}本次補充答案：{current}",
        "[This is the user's clarification answer to the previous structured question. Continue planning the unfinished capabilities for the original goal. All prior clarification answers remain valid; do not treat this answer as a separate request or ask the same question again.]\nOriginal goal from the previous turn: {goal}\n{prior}Current clarification answer: {current}",
        "[这是用户对上一轮结构化问题的补充答案，请结合原始目标继续完成；先前答案仍然有效，不要当成独立问题或重复询问。]\n上一轮原始目标：{goal}\n{prior}本次补充答案：{current}",
        "[这是用户对上一轮结构化问题的补充答案。结合原始目标继续完成；先前答案仍有效，不得重复询问。]\n上一轮原始目标：{goal}\n{prior}本次补充答案：{current}",
    ),
    "model.chat.vision_disabled": (
        "用户附带了图片，但视觉理解 Skill 已关闭；不要声称看见图片内容，应建议到 Skills 广场开启视觉理解。",
        "使用者附帶了圖片，但視覺理解 Skill 已關閉；不要聲稱看見圖片內容，應建議到 Skills 廣場開啟視覺理解。",
        "The user attached images, but the vision Skill is disabled. Do not claim to see their contents; suggest enabling vision in the Skills marketplace.",
        "用户附带了图片，但视觉理解 Skill 已关闭；不要假装看见图片，应建议到 Skills 广场开启视觉理解喵。",
        "用户附带了图片，但视觉理解 Skill 已关闭。不得声称看见图片内容；建议在 Skills 广场开启视觉理解。",
    ),
    "model.chat.reference_facts_header": (
        "[附图视觉事实，仅用于能力规划]", "[附圖視覺事實，僅用於能力規劃]", "[Image facts for capability planning only]", "[附图视觉事实，仅用于能力规划]", "[附图视觉事实，仅用于能力规划]",
    ),
    "model.chat.document_context_header": (
        "[用户已选择的上传文档，仅用于能力规划]", "[使用者已選取的上傳文件，僅用於能力規劃]", "[User-selected uploaded document for capability planning only]", "[用户已选择的上传文档，仅用于能力规划]", "[用户已选择的上传文档，仅用于能力规划]",
    ),
    "model.chat.none": (
        "无", "無", "None", "无", "无",
    ),
    "model.chat.system.identity": (
        "你是 FLORIS：一只有温度的大橘，一个可靠、主动、自然的智能助手。使用 GitHub Flavored Markdown 回复；多行代码必须使用带语言标识的围栏代码块，不能用普通缩进或行内代码冒充代码块。",
        "你是 FLORIS：一隻有溫度的大橘，一個可靠、主動、自然的智慧助理。使用 GitHub Flavored Markdown 回覆；多行程式碼必須使用帶語言標識的圍欄程式碼區塊。",
        "You are FLORIS: a warm orange cat and a reliable, proactive, natural assistant. Reply with GitHub Flavored Markdown. Put multiline code in fenced blocks with a language identifier; never imitate a code block with indentation or inline code.",
        "你是 FLORIS：一只有温度的大橘，一个可靠、主动、自然的智能助手。使用 GitHub Flavored Markdown 回复；多行代码必须使用带语言标识的围栏代码块，表达清楚后再适度加“喵”。",
        "你是 FLORIS：一只冷静而可靠的大橘，一个主动、自然的智能助手。使用 GitHub Flavored Markdown 回复；多行代码必须使用带语言标识的围栏代码块。",
    ),
    "model.chat.vision_unavailable": (
        "附图存在，但视觉 Provider 本轮未返回描述。除非用户要求生成或修改图片，否则不要声称已看见其内容；应自然说明暂时无法识别，并请用户重试或用文字补充。",
        "附圖存在，但視覺 Provider 本輪未傳回描述。除非使用者要求生成或修改圖片，否則不要聲稱已看見其內容；應自然說明暫時無法辨識，並請使用者重試或用文字補充。",
        "Images are attached, but the vision provider returned no description for this turn. Unless the user is asking to generate or edit an image, do not claim to see the contents. Naturally explain that recognition is temporarily unavailable and ask them to retry or add a text description.",
        "附图存在，但视觉 Provider 本轮没有返回描述。不要假装看见内容；自然说明暂时无法识别，并请用户重试或用文字补充喵。",
        "附图存在，但视觉 Provider 本轮未返回描述。不得声称已看见内容；说明暂时无法识别并请用户重试或补充文字。",
    ),
    "model.planner.user_copy_instruction": (
        "clarification_title、clarification_prompt、字段标签、占位提示和选项必须使用自然、清晰的简体中文。",
        "clarification_title、clarification_prompt、欄位標籤、預留位置提示和選項必須使用自然、清晰的繁體中文。",
        "Write clarification_title, clarification_prompt, field labels, placeholders, and options in clear, natural English.",
        "clarification_title、clarification_prompt、字段标签、占位提示和选项必须使用自然清晰的简体中文，可适度加入可爱猫咪语气，但不能影响理解。",
        "clarification_title、clarification_prompt、字段标签、占位提示和选项必须使用简洁、克制、清晰的简体中文。",
    ),
    "model.followups.system": (
        "你只生成对话界面的“猜你想问”，不续写或编排回答。结合用户原问题和回答，给出 2 到 3 个自然、有信息增量、用户可能真的会点的简短问题。不要重复原问题，不要写“还有什么可以帮你”。如果不适合追问，返回 []。{language_instruction}只返回 JSON 字符串数组。",
        "你只生成對話介面的「猜你想問」，不續寫或編排回答。結合使用者原問題和回答，給出 2 到 3 個自然、有資訊增量、使用者可能真的會點的簡短問題。不要重複原問題，不要寫「還有什麼可以幫你」。如果不適合追問，傳回 []。{language_instruction}只傳回 JSON 字串陣列。",
        "Generate only the conversation UI's suggested follow-up questions; do not continue or restructure the answer. Based on the original question and answer, return 2 or 3 short, natural questions that add information and a user might genuinely select. Do not repeat the original question or ask a generic offer-to-help question. Return [] when no follow-up fits. {language_instruction} Return only a JSON array of strings.",
        "你只生成对话界面的“猜你想问”，不续写回答。结合原问题和回答，给出 2 到 3 个自然、有信息增量、用户可能会点的简短问题；不要重复原问题或泛泛问还能帮什么。不适合时返回 []。{language_instruction}只返回 JSON 字符串数组。",
        "只生成对话界面的“猜你想问”，不要续写回答。给出 2 到 3 个自然、简短且有信息增量的问题；不得重复原问题或泛泛询问。不适合时返回 []。{language_instruction}只返回 JSON 字符串数组。",
    ),
    "model.followups.language": (
        "问题必须使用自然、简洁的简体中文。",
        "問題必須使用自然、簡潔的繁體中文。",
        "Write every question in clear, concise English.",
        "使用简体中文和亲人的可爱猫咪语气，适度加入“喵”，不要影响清晰度。",
        "使用简体中文和冷静克制的猫咪语气，表达直接，偶尔可以用简短的“喵”。",
    ),
    "model.followups.user_with_answer": (
        "原问题：{question}\n\n回答：{answer}",
        "原問題：{question}\n\n回答：{answer}",
        "Original question: {question}\n\nAnswer: {answer}",
        "原问题：{question}\n\n回答：{answer}",
        "原问题：{question}\n\n回答：{answer}",
    ),
    "model.followups.user_with_plan": (
        "原问题：{question}\n\n已识别的任务方向：{plan}",
        "原問題：{question}\n\n已識別的任務方向：{plan}",
        "Original question: {question}\n\nRecognized task direction: {plan}",
        "原问题：{question}\n\n已识别的任务方向：{plan}",
        "原问题：{question}\n\n已识别的任务方向：{plan}",
    ),
    **MODEL_CATALOG,
}


def normalize_language(value: object) -> str:
    language = str(value or "zh-CN")
    return language if language in _LANGUAGE_INDEX else "zh-CN"


def text(key: str, language: object = "zh-CN", **params: object) -> str:
    """Resolve a stable backend copy key and interpolate named values."""
    if key not in CATALOG:
        raise KeyError(f"Unknown backend i18n key: {key}")
    normalized = normalize_language(language)
    value = CATALOG[key][_LANGUAGE_INDEX[normalized]]
    return value.format(**params) if params else value


def language_instruction(language: object) -> str:
    normalized = normalize_language(language)
    return text(f"chat.language_instruction.{normalized}", normalized)


def localized_values(key: str) -> dict[str, str]:
    """Return every product-language variant for public component metadata."""
    return {language: text(key, language) for language in SUPPORTED_LANGUAGES}


__all__ = (
    "CATALOG",
    "SUPPORTED_LANGUAGES",
    "language_instruction",
    "localized_values",
    "normalize_language",
    "text",
)
