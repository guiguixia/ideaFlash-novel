# 剧本刷 · ScriptRun

私有互动故事创作与体验平台。

当前版本：`0.1.1`

用户可以创建原创故事，或导入小说、影视文本资料；它们都会进入统一的作品工作台。导入小说可选择连续章节生成体验副本，原创故事可从开局设定生成体验版本。默认数据保存在本机；启用微信入口后，能向该机器人发消息的用户可浏览当前实例中的作品。

产品交互与术语以 [DESIGN.md](DESIGN.md) 为准。

## 0.1.1 新增：角色桌宠

- 在「角色」页为副本专属角色卡配置默认、思考、疑惑、开心、低落五个固定形象槽位；默认形象必填，并可额外新增最多 5 个可命名的角色专属状态。
- 桌宠可拖动窗口、拖拽四角调整大小；角色回复会以气泡显示在角色图左侧并自动渐隐。
- 可在桌宠中直接给角色留言，也可打开私聊面板查看历史、切换指定私聊会话并继续对话；发送时会显示思考形象，角色回复会按情绪自动切换对应图片，未配置时回退默认形象。
- 角色私聊独立于体验剧情，不会改写副本体验记录；角色形象与私聊记录均保存在本机。
- 新建或重新构建的副本会从原文提取角色短对白并保留来源章节；私聊每次选取少量对白作为口吻参考，不会照抄台词或把其中事件当作当前事实。

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

### 微信入口

在「设置 → 微信入口」扫码连接机器人后，微信用户可通过文字菜单进入当前本机的剧情体验与角色私聊：

- `【作品】`：列出作品并选择当前作品；
- `【剧情】`：列出当前作品的体验副本，选择后直接发送行动推进剧情；
- `【私聊】`：选择角色、新建或续聊该角色的私聊会话；
- `【首页】` 或 `【退出】`：结束当前模式并回到欢迎页。

微信入口与桌面端共用同一批剧情和角色私聊会话，适合单人本地使用。此入口不提供账号绑定或访问控制；请勿在启用后放入私密作品。

## 数据迁移

本版本会在首次启动时清理旧小说工作台、章节生产、扫榜和参考作品相关的数据表，然后创建新的作品、来源片段、体验副本和体验会话表。旧数据不保留。

## 桌面应用

项目已支持封装为 Electron 桌面应用。安装包内包含前端与 FastAPI 本地服务，最终用户无需安装 Node.js 或 Python；作品、体验记录和模型配置仍只存放在本机。

### 下载体验

- [Windows / macOS 安装包下载（百度网盘）](https://pan.baidu.com/s/14M4s5NJeBUrW-UHvjG3Wnw?pwd=1111)，提取码：`1111`

下载后直接安装即可。首次启动时，在「设置」中填写兼容 OpenAI 的模型服务地址、模型名与 API Key。

交流反馈：QQ 讨论群 `1097381307`。

微信讨论群（扫码加入）：

<img src="docs/images/ideaFlash-script-run-qq-group.png" alt="剧本刷微信讨论群二维码" width="280" />

### 桌面开发

完成本地开发环境准备后，执行：

```bash
npm run desktop:dev
```

Electron 会自动启动本地 API 服务，同时加载 Vite 开发页面。

若 5179 端口已有本项目的 Vite 服务在运行，该命令会直接复用它启动 Electron，不会因端口占用而失败。前端改动可直接调试；涉及 Electron 主进程或预加载脚本的改动，需要重启调试窗口。

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

- macOS：`~/Library/Application Support/剧本刷/novel.db`
- Windows：`%APPDATA%/剧本刷/novel.db`

从旧版 `IdeaFlash Story` 升级时，桌面应用会在首次启动自动迁移原有本地数据。

### 自动更新

默认不启用自动更新，适合本地测试或手动分发。需要对外发布时：

1. 准备 HTTPS 对象存储或 CDN 作为更新源。
2. 在 [desktop/update-config.json](desktop/update-config.json) 设置 `baseUrl`。
3. 用同一更新根地址构建并上传更新产物：

   ```bash
   NOVEL_UPDATE_BASE_URL=https://updates.example.com/script-run npm run desktop:make
   ```

正式自动更新需要 macOS Developer ID 签名与公证；Windows 也建议配置代码签名证书。完整发布目录、版本迁移与回滚规则请见 [桌面应用与自动更新文档](docs/desktop-distribution.md)。
