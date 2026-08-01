# FLORIS 功能文档
<img width="1691" height="1079" alt="b31aaad03ef82f8af8609eb649ddbe4e" src="https://github.com/user-attachments/assets/7c0778ef-82a3-4b58-98b3-d2de6fccd77d" />

> 产品名：**FLORIS：一只有温度的大橘**
> 
> 作者：**Jurant** && **Jimmy**
> 
> 产品介绍：<https://floris.jlutx.com>
>
> AI 对话：<https://floris.jlutx.com/chatBot>
>
> 运行平台：腾讯云 EdgeOne Makers
>
> 产品简介：一只橘猫，它很温柔，喜欢和你聊天。它能细心地给你安排日程，安排旅游，它能告诉你每天有什么新鲜事，会贴心地提醒你天寒加衣，emm...有时候你做着无聊的科研，它会依在你身边，帮你翻译总结，早点晚安。你和它聊天，它绝对会给你它所知的一切，会尽可能用各种形式让你听懂。会在你看不懂外文时做你的喵喵翻译机。当然它还是一个画家，可以为你画出你脑海的星空。大橘，一个真的懂你黏你的喵～

## 1. 如何配置我们的项目？

### 1.1 进入EdgeMaker控制台并创建项目
进入 [EdgeMaker 控制台](https://console.cloud.tencent.com/edgeone/makers)，关联 GitHub 后创建项目并选择仓库和分支。

- 正式基线项目使用 `main`。
- 架构开发与验收必须新建独立 Maker 项目（例如 `floris-mvc-dev`），且只绑定 `dev`。
- **不得把 `dev` 绑定、部署或改配到现有 `ai-active-agent-floris` 项目。** 两个项目的项目 ID、部署记录、域名和环境变量彼此独立。

### 1.2 配置环境变量
**第一步**，点击已创建好的项目

<img width="600" height="400" alt="image" src="https://github.com/user-attachments/assets/4ecce1f8-ca55-4ba1-bf25-8828402e6626" />


**第二步**，点击**项目设置**，找到**环境变量**

<img width="600" height="400" alt="image" src="https://github.com/user-attachments/assets/fce7ab99-a4be-4b05-aab7-79c6d15edf6c" />

**第三步**，按照下表配置环境变量

| 变量名                 | 变量值    | 备注                         | 生效范围 |
| ---------------------- | --------- | ---------------------------- | -------- |
| WSA_API_KEY            | ********* | 内容搜索                           | 全部环境 |
| AI_GATEWAY_API_KEY     | ********* | -                            | 全部环境 |
| VITE_TENCENT_MAP_KEY   | ********* | 腾讯地图前端构建                            | 全部环境 |
| HUNYUAN_IMAGE_API_KEY  | ********* | 混元视觉模型                            | 全部环境 |
| DEEPSEEK_API_KEY       | ********* | Deepseek语言模型                            | 全部环境 |
| TENCENT_MAP_SERVER_KEY | ********* | 腾讯地图服务                            | 全部环境 |
| AI_GATEWAY_BASE_URL    | ********* | -                            | 全部环境 |
| JWT_SECRET             | ********* | 至少 32 字符；签名多用户/Guest 会话   | 全部环境 |
| DEFAULT_TENANT_ID      | floris    | 默认租户标识                           | 全部环境 |
| CLOUDBASE_ENV_ID       | floris-auth-d3gd1pvebd6321d35 | CloudBase 身份环境；当前值也有代码默认值 | 全部环境 |
| CLOUDBASE_REGION       | ap-shanghai | CloudBase 身份地域                    | 全部环境 |
| DATABASE_URL           | ********* | 仅旧微信通道使用的 Neon 连接（可选）     | 全部环境 |
| WECHAT_OPEN_APP_ID     | ********* | 微信开放平台网站应用 ID（可选）         | 全部环境 |
| WECHAT_OPEN_APP_SECRET | ********* | 微信开放平台密钥（仅服务端，可选）       | 全部环境 |
| WECHAT_OPEN_CALLBACK_URL | ********* | 微信 OAuth 回调地址（可选）           | 全部环境 |
| WECHAT_OFFICIAL_ACCOUNT_APP_ID | ********* | 微信公众号 App ID（微信内一键登录，可选） | 全部环境 |
| WECHAT_OFFICIAL_ACCOUNT_APP_SECRET | ********* | 微信公众号 App Secret（仅服务端，可选） | 全部环境 |
| WECHAT_OFFICIAL_ACCOUNT_CALLBACK_URL | ********* | 公众号网页 OAuth 回调地址（可选） | 全部环境 |

当前主登录使用 CloudBase 内置邮箱验证码，GitHub 是次级入口，游客无需登录即可正常聊天。前端只使用 CloudBase Publishable Key；它会随 Vite 构建公开，不能替换为 SecretId、SecretKey 或管理员 token。登录后的 CloudBase access token 会交给 `/auth/cloudbase/session`，由服务端调用官方 `/auth/v1/user/me` 验真后再签发 Floris 自己的 HttpOnly 会话，浏览器资料和 CloudBase 用户组不会被直接信任为 Floris 权限。

在 CloudBase PostgreSQL 的 SQL 编辑器依次执行 `db/migrations/001_identity_and_entitlements.sql` 和 `db/migrations/002_cloudbase_identity_adapter.sql`，即可把首次登录前的 Guest subject 原子绑定到正式账号，并保留 Makers Conversation、Store 与 Blob 的既有命名空间。迁移尚未执行时，登录会安全降级为按 CloudBase UID 确定性派生的 Floris subject，不阻塞登录或游客聊天，但无法保留首次登录前的 Guest 历史。

CloudBase「环境配置 → 安全来源」还需加入当前开发站域名（只填域名、不带 `https://`）。GitHub OAuth 的 `redirectTo` 也必须属于该安全域名。自定义域名后再追加正式域名即可，不要求现在为了开发登录提前注册域名。

微信登录代码保留为可选兼容 Adapter，但当前不开启。以后启用时，仍需独立的微信开放平台/公众号凭据和 `DATABASE_URL`；小程序凭据不能替代它们。缺失配置不会影响 CloudBase 登录或 Guest 模式。

### 1.3 Preview or Production 部署

**Preview 流程：**
**第一步**，点击已创建好的项目

<img width="600" height="400" alt="image" src="https://github.com/user-attachments/assets/4ecce1f8-ca55-4ba1-bf25-8828402e6626" />

**第二步**，点击**构建部署**，再点击**新建部署**

<img width="600" height="400" alt="image" src="https://github.com/user-attachments/assets/02a35773-1a34-4c21-8bbc-023385169b15" />

**第三步**，在独立开发项目中选择 **dev 分支**并创建 Preview。正式项目仍只跟踪 **main 分支**。点击确定后等待部署成功。

<img width="600" height="400" alt="image" src="https://github.com/user-attachments/assets/3b5767d1-d57e-43de-961d-9e20c9f4051b" />

**Production 流程：** 只有经过明确合并发布决策后，才在正式项目的 `main` 上操作。不要为了测试 `dev` 修改 `ai-active-agent-floris` 的分支、环境变量或域名。

若使用 CLI 创建“直接上传型”独立开发项目，Makers 要求该项目先完成一次 Production 初始化，之后才能创建 Preview。这里的 Production 仅指**新开发项目自己的环境**：项目名必须唯一，上传内容必须来自已推送的 `dev` 提交，仍不得复用或改配正式项目。

直接上传前必须验证 Maker 实际生成的 Agent 路由，再部署同一份已经验证的构建产物：

```bash
edgeone makers build
npm run test:edgeone-build-routes
npm run check:deploy-target
edgeone makers deploy .edgeone -n floris-mvc-dev-5925b93 -e preview --json
```

本仓库的开发部署守卫还会核对项目 ID `makers-x91pbqwetj8l`、当前分支
`dev`、干净工作区以及未变化的 `main` 基线。CLI 首次初始化限制只适用于
独立开发项目自身；日常架构验收始终部署 Preview。

Skill 广场使用 `/skill_marketplace`；不要使用 EdgeOne 保留的
`agents/skills/`。可信 Python 适配器放在 `agents/_skill_adapters/`，避免
Makers 将其自动发布为无意的 HTTP 路由。

## 2. 如何直接体验我们的项目？
### 2.1 开始一个新的对话！
废话不多说，直接上图（这个在你刚进去的时候，可爱的Floris也会贴心为你介绍哦~）

<img width="1617" height="1079" alt="c624dda44eb7b2ab78023613250490a3" src="https://github.com/user-attachments/assets/e7755c28-de1e-4491-a03a-eff66beeff17" />

### 2.2 Skill工厂

<img width="1770" height="867" alt="image" src="https://github.com/user-attachments/assets/2536c220-be5f-4c29-b21d-5fbb53757121" />

打开全页 **Skill 广场**，可查看全部/已安装 Skill、依赖图、组件 API 文档，并下载已安装的标准包。**通用问答与创作**和**主动式 Agent**是游客也可使用的必开系统 Skill；其他 Skill 需要登录并按会员权益安装。游客请求实时资讯但没有实时搜索权益时，不会被安装提示打断，而是明确无法实时核验并由基础模型继续回答。内置能力统一使用 `SKILL.md + floris.json`，用户 ZIP 只会进入 Makers Blob 的待审核区，审核后台完成前不会安装或执行。

### 2.3 设置

<img width="1610" height="872" alt="image" src="https://github.com/user-attachments/assets/e1329669-d038-4102-82c3-2789874d05ed" />

打开**设置**
- 可选择**界面语言**，可以选择**可爱喵喵语**，这和我们的 Floris 更搭。
- 可体验**新人介绍**，更好地了解Floris。
- 可看到模型的额度与用量。
- 对于富搜索可改善体验，希望快一些可以将**网页结果数量**和**候选图片数量**调低。
- 算了不写了喵，接下来的你们自己看就完了。

## 3. 我们的项目都有啥功能？

### 3.1 富文本加强搜索
假如你问Floris，最近AI有啥新消息？

它可能会这样回答你：

<img width="200" height="750" alt="84e259148afd4796d810fe725c11eb4c" src="https://github.com/user-attachments/assets/2ea918de-de9f-4629-adfd-e688f82986bb" />

它用最直白，最靠谱，最实时的方式回复你，让回答的含金量直线提升。

### 3.2 路程规划 && 地点搜索
现代年轻人大多焦虑，焦虑什么呢？

当然是晚上去哪吃？附近有什么？周末去哪玩？

有了Floris，这些都不再是问题！假如你问：我附近有啥玩的？

<img width="812" height="631" alt="image" src="https://github.com/user-attachments/assets/d5b69df1-0db0-49b1-ba5f-19aa893c822f" />

它会为你准确的回答，并且还能帮你把这些标注在地图上。可点击最下方的**查看地点**就可以在地图上查看啦！

当然，你也可以对它说：我明天就想去这些地方玩！

<img width="387" height="405" alt="image" src="https://github.com/user-attachments/assets/5651cebd-bb51-4913-8fd0-c166c02b80b6" />

它会贴心地帮你把行程都规划好，真正实现“你以为的岁月静好，其实是有喵为你负重前行”。

### 3.3 日程规划
你以为这就完了？当你旅游意愿特别强烈时，Floris还会贴心为你制定一个明天的日程，并在合适的时机提醒你。

<img width="365" height="353" alt="image" src="https://github.com/user-attachments/assets/4005f3f8-d3e1-4ebe-b289-b567ac397c6f" />

你以为这就完了？你甚至还可以让Floris自动为你更改日程，比如你说：

<img width="952" height="341" alt="image" src="https://github.com/user-attachments/assets/4a972e8c-2d23-4029-a56a-5f3a8d0346d1" />

真就是你只管考虑玩就行了，Floris考虑的就多了。
### 3.4 论文 && 文档助读
是不是还在熬夜看论文呢？Floris也会助你一臂之力哦~，首先它会帮你收集文献。

你可以这样说：“给我找两篇XX老师的论文XX方向的”

<img width="1050" height="665" alt="image" src="https://github.com/user-attachments/assets/85e37e7b-5d66-4f0d-b68a-4933ada89df8" />

当然，Floris还会为你提供一个超级方便的论文助读器，可总结，可翻译，是科研DOG的得力助手。

<img width="1912" height="876" alt="image" src="https://github.com/user-attachments/assets/669513bf-832f-4a01-9264-69eb0b4f7cd7" />

### 3.5 主动式Card
Floris不会忽悠你，所谓知之为知之，不知为不知，是知也。当Floris遇到它无法推断的问题会主动向您提问，提问的方式也很友好，它会给你发若干张卡片，你填好它就继续思考啦。

比如这样：

<img width="922" height="490" alt="image" src="https://github.com/user-attachments/assets/380aa4e3-8daf-460b-91b6-ea3672e0e4f7" />

Floris会向你询问它不知道的内容，从而给你最靠谱的答案。

### 3.6 图片工坊
Floris不仅是你的好伙伴，它还是一个大画家，你可以让它画世间万物。

比如，我们让它画个难点的：“请帮我画一个你”

<img width="762" height="637" alt="image" src="https://github.com/user-attachments/assets/4967ebae-069f-4c07-8144-ff706ca06d9e" />

它真的做到了！这时，你可以对它说一个更有难度的，“让表情变得凶狠！”

<img width="552" height="652" alt="image" src="https://github.com/user-attachments/assets/b697318b-c73a-48a4-a90e-95276fbcd137" />

它还会给你相似图片的对比图，为你提供左右两种按键，方便对比！

### 3.7 Skill分离设计
Floris 的技能是独立、可安装并有依赖关系的标准包。系统 Skill 与未来审核通过的用户 Skill 都通过最小权限组件 API 工作，身份、租户、会员和副作用确认由服务端确定性校验，不交给模型判断。详细的修改前/后架构图、MVC 边界和优先级见 [ARCHITECTURE_PLAN.md](./ARCHITECTURE_PLAN.md)。

### 3.8 一些用户友好的功能
- Floris会从你的行程，你的喜欢，你的习惯推测一些事情分享给你，它会把这些写到醒目的位置
- Floris会对你阅读的文献自动整理，自动为你创建文件夹。
- Floris可以调整白天和黑夜，保护您的眼睛。

## 4. Floris 目前有待提升的能力
- 目前Floris还是一直懒猫，有的时候回答你会很慢，它的主人正在努力地优化，请不要着急！
- Floris有的时候为了更好的回答您的问题，想的太多，所以在超时的时候有小概率回答你“模型上下文请求失败”（好吧，这不是Floris回答的，单纯是程序崩了...没关系，再问一次就行啦！
- Floris的所有问题，都可以发邮件给[2011948918@qq.com](2011948918@qq.com)，我们希望Floris更好，快点赶上哆啦A梦！
## 5. 致谢
首先先感谢我的老朋友**Codex**，经常没日没夜为我测试找BUG，直到现在，已经凌晨1点了，它也没有休息！其次感谢我的新朋友**Kimi3**，为我设计了Floris的前端，很丝滑！然后，感谢我们组的苦力**Deepseek**，除了主办方给的免费AI额度，就全都是你了，没办法，你实在太便宜了！然后，感谢我的人类朋友**Jimmy**，这几天我们聊的很多，聊梦想，聊未来，聊北京，感谢与我合作，我们创造了Floris! 最后，感谢**腾讯**，梦中情司，感谢你为我提供资源，圆了我的梦想，感谢你为我提供福利，让我每天都很开心！
