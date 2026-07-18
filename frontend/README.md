# 元宝前端

React 18 + TypeScript + Vite 前端，由 EdgeOne Makers 统一提供静态资源、Cloud Functions 和 Python Agent 路由。前端不包含 FastAPI、WebSocket 或旧 `/api` 回退。

## 开发命令

从仓库根目录执行：

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

Vite 默认地址为 `http://127.0.0.1:5173/`。该模式适合组件和静态测试站布局开发，但没有 Makers Agent/Cloud Functions；完整联调请回到仓库根目录运行：

```bash
edgeone makers dev
```

并使用 CLI 输出的统一代理地址。

## 测试与构建

```bash
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build -- --mode edgeone
```

构建输出位于 `frontend/dist/`，不得提交仓库。

## 测试 Case 页面

源文件位于 `public/test-cases/`，构建后入口是 `/test-cases/`。

- Vite 静态检查：`http://127.0.0.1:5173/test-cases/index.html`。Vite 不应用 EdgeOne rewrite，必须保留 `index.html`；此模式只使用浏览器本地兜底。
- Makers 完整检查：运行根目录 `edgeone makers dev`，访问统一代理的 `/test-cases/`。支持 `/acceptance`、Makers Blob、多主机同步和证据上传。
- EdgeOne Preview：从 Deployment 的“预览”按钮取得签名链接，再访问同域 `/test-cases/`，保留 `eo_token`、`eo_time`。

完整说明见 [`../docs/TESTING.md`](../docs/TESTING.md) 和 [`../docs/ACCEPTANCE_SITE.md`](../docs/ACCEPTANCE_SITE.md)。
