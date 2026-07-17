# 腾讯会议持久桥

腾讯会议官方 CLI 的 OAuth 凭据使用系统 Keychain 且与设备绑定，不能复制进 EdgeOne 构建产物。因此 EdgeOne 通过 HTTPS 调用这台持久机器，最终仍由旧方案的 `tmeet meeting create` 创建会议，用户不需要逐次授权。

在持久 Linux/macOS/Windows 主机上：

1. 安装 Node.js 和 `npm install -g @tencentcloud/tmeet`。
2. 由会议账号管理员执行一次 `tmeet auth login`。
3. 设置一个高强度随机 `MEETING_BRIDGE_TOKEN`。
4. 安装本目录依赖，运行 `uvicorn app:app --host 127.0.0.1 --port 8090`。
5. 使用 Nginx/Caddy 提供 HTTPS，只转发 `/health` 与 `/v1/meetings`。
6. 在 Makers 环境中设置 `MEETING_BRIDGE_URL=https://你的域名/v1/meetings` 和同一个 `MEETING_BRIDGE_TOKEN`。

不要复制、上传或提交 `~/.tmeet` 和系统 Keychain 数据。
