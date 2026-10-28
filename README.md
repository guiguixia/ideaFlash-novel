# ideaFlash Story

私有互动故事创作与体验平台。

用户可以创建原创故事，或导入小说、影视文本资料；它们都会进入统一的作品工作台。导入小说可选择连续章节生成体验副本，原创故事可从开局设定生成体验版本。所有作品、体验副本和会话均仅本人可访问。

产品交互与术语以 [DESIGN.md](DESIGN.md) 为准。

## 本地开发

```bash
cp .env.example .env
npm install
cd backend && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd .. && npm run dev
```

也可以使用：

```bash
NOVEL_SKIP_PULL=1 NOVEL_SKIP_INSTALL=1 bash script/restart.sh
```

停止本地前后端服务：

```bash
bash script/stop.sh
```

如使用了自定义端口，停止时传入同一组端口：

```bash
NOVEL_API_PORT=8005 NOVEL_WEB_PORT=5180 bash script/stop.sh
```

- Web：<http://127.0.0.1:5179>
- API：<http://127.0.0.1:8004/docs>

本地版本不需要登录。首次进入会引导配置 OpenAI 兼容服务地址、模型和 API Key；模型配置仅保存在本机数据库中。微信入群二维码默认使用仓库内置的公开 OSS 地址；部署时可通过 `NOVEL_COMMUNITY_QR_IMAGE_URL` 覆盖。

## 数据迁移

本版本会在首次启动时清理旧小说工作台、章节生产、扫榜和参考作品相关的数据表，然后创建新的作品、来源片段、体验副本和体验会话表。旧数据不保留。

## 桌面应用

项目已支持封装为 Electron 桌面应用。安装包内包含前端与 FastAPI 本地服务，最终用户无需安装 Node.js 或 Python；作品、体验记录和模型配置仍只存放在本机。

### 桌面开发

完成本地开发环境准备后，执行：

```bash
npm run desktop:dev
```

Electron 会自动启动本地 API 服务，同时加载 Vite 开发页面。

### 构建安装包

```bash
npm run desktop:make
```

该命令依次构建前端、使用 PyInstaller 编译 FastAPI sidecar，并使用 Electron Forge 生成当前系统的分发包：

- macOS：`out/make/*.dmg`（首次安装）和 `out/make/zip/**/*.zip`（自动更新）。
- Windows：`Setup.exe`、`.nupkg` 和 `RELEASES`。

也可以使用系统专用脚本；它们会从前端、Python sidecar 一直构建到最终分发包：

```bash
# macOS（当前机器架构；可用 NOVEL_DESKTOP_ARCH=arm64 或 x64 覆盖）
npm run desktop:make:mac

# Windows PowerShell（默认 x64）
npm run desktop:make:win
```

Windows 安装包必须在 Windows 上构建；macOS 安装包建议在对应架构的 macOS 上构建。

桌面版数据库位于系统用户数据目录，升级安装包不会覆盖现有数据：

- macOS：`~/Library/Application Support/IdeaFlash Story/novel.db`
- Windows：`%APPDATA%/IdeaFlash Story/novel.db`

### 自动更新

默认不启用自动更新，适合本地测试或手动分发。需要对外发布时：

1. 准备 HTTPS 对象存储或 CDN 作为更新源。
2. 在 [desktop/update-config.json](desktop/update-config.json) 设置 `baseUrl`。
3. 用同一更新根地址构建并上传更新产物：

   ```bash
   NOVEL_UPDATE_BASE_URL=https://updates.example.com/ideaflash-story npm run desktop:make
   ```

正式自动更新需要 macOS Developer ID 签名与公证；Windows 也建议配置代码签名证书。完整发布目录、版本迁移与回滚规则请见 [桌面应用与自动更新文档](docs/desktop-distribution.md)。
