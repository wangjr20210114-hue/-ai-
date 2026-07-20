# 腾讯会议可选连接器

腾讯会议不是个人演示的发布阻塞项。代码只有在五项凭据完整时才向模型暴露创建会议工具。

## 个人账号能否直接取得

普通个人免费账号通常不能在客户端中直接生成服务端 API 的 SecretId/SecretKey。可行路径只有：

1. 使用商业版、企业版或教育版组织，由企业管理员在“企业管理 → 高级 → 应用管理”创建企业自建应用并取得凭据。
2. 在腾讯会议开放平台申请第三方开发者并通过审核；个人开发者可申请，但审核与能力开通不保证通过。

官方入口：

- 企业自建应用前提与凭据：[腾讯云 API 文档](https://cloud.tencent.com/document/product/1095/42407)
- AppId/SdkId 说明：[腾讯云基本概念](https://cloud.tencent.com/document/product/1095/79796)
- 开放平台申请：[腾讯会议开放平台](https://meeting.tencent.com/open-api/)
- 第三方开发者申请说明：[成为开发者](https://meeting.tencent.com/support/topic/2160/)

## 环境变量对应关系

| 项目变量 | 腾讯会议后台字段 |
| --- | --- |
| `TENCENT_MEETING_SECRET_ID` | 自建应用 SecretId |
| `TENCENT_MEETING_SECRET_KEY` | 自建应用 SecretKey |
| `TENCENT_MEETING_APP_ID` | 企业 AppId |
| `TENCENT_MEETING_SDK_ID` | 应用 SdkId |
| `TENCENT_MEETING_USER_ID` | 企业通讯录中已注册的用户 userid，不能随意填写昵称 |

无法取得上述凭据时保持变量为空即可；普通日程、主动提醒和其余核心能力不受影响。
