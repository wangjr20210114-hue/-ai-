# 结构化图文回答

## 目标

回答可以自然排版文字、图片和来源，但模型不能凭空引入媒体，也不能让广告、二维码、Logo 或关键词误匹配图片混入结果。

## 数据流

```text
平台搜索
  └─► 来源与候选页面
       └─► 页面正文和媒体提取
            ├─► URL/尺寸/重复项基础校验
            └─► 混元视觉模型读取实际画面
                  ├─ 广告/二维码/Logo/装饰图：丢弃
                  └─ 与问题高度相关：进入可信 media 白名单

可信来源 + 正文摘要 + media
  └─► 文本模型自由生成标准 Markdown
       └─► 前端仅渲染白名单 URL
```

## 关键实现

- `agents/chat/_rich_search.py`：来源整理、页面提取、媒体候选和并发视觉审核。
- `agents/chat/index.py`：隔离内部视觉模型流、发送结构化搜索元数据。
- `frontend/src/services/search.ts`：规范化搜索事件。
- `frontend/src/components/common/richContent.ts`：可信 URL 和媒体映射。
- `frontend/src/components/common/MarkdownRenderer.tsx`：安全渲染 Markdown 与媒体说明。

## 安全约束

- 不按关键词决定图片相关性；关键词只可用于检索候选，最终画面必须经过视觉模型。
- 视觉模型只做保留/丢弃判断，不生成事实性描述或回答内容。
- 任一视觉审核失败时保守丢弃图片，不因“可能相关”放行。
- 回答中的图片、链接必须绑定当前消息的 `search_results.results/media`。
- 内网、非 HTTP(S)、未知来源和不在白名单中的 URL 不渲染。
- 模型工具协议、视觉审核输出和内部媒体 ID 不进入用户正文。
- 搜索提示只描述阶段，不暴露查询编排、候选选择和工具参数。

## 协议

富搜索使用 `schema_version: 3`：

- `results`：来源标题、摘要和 URL；
- `media`：通过审核的图片及来源绑定；
- `sources_used`：实际采用的来源类型；
- `total`：来源数量。

模型输出标准 Markdown 原始 URL，前端以同消息元数据为授权清单。项目不再支持旧 `[[image:...]]` 标记或本地 WebSocket v1 媒体协议。
