---
name: calendar
description: 读取当前用户日程，并用版本化确认卡新增、修改或删除日程。
---

# Calendar

只读或汇总当前日程使用 `needs_calendar_context`；新增、修改或删除还需要 `needs_calendar_action`。可编辑日程提案也属于动作能力，因为它生成待用户确认的提案而不是自动提交。

现实地点未核实时先调用地点核验。日程始终是独立提案，必须经过冲突检查、版本校验和用户确认；不得由模型或 Skill 直接提交副作用。
