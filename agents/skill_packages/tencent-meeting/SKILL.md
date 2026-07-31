---
name: tencent-meeting
description: 通过腾讯会议官方个人 AI Skill 创建真实会议，并把结果写入日程提案。
---

# Tencent Meeting

创建腾讯会议时使用会议动作；普通日程不需要会议链接时不得调用。该 Skill 强依赖 `calendar`，必须先安装并启用日程 Skill。

Token 只能存储在服务端受限状态中，不能回传前端或写入日志。真实会议创建仍必须经过 Floris 的用户确认、幂等账本和失败核对流程。
