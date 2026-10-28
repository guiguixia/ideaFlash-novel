# 桌面应用与自动更新

## 目标

将剧本刷（ScriptRun）发布为私有本地桌面应用：用户下载安装包后，无需安装 Node.js 或 Python，即可在本机使用。作品、体验副本、会话和大模型配置始终存放在本机，不上传到更新服务。

## 运行结构

```text
Electron 主进程
├── React/Vite 静态前端（resources/dist）
├── FastAPI sidecar（PyInstaller: novel-server）
│   └── 仅监听 127.0.0.1:8004
└── 用户数据目录
    └── novel.db
```

Electron 启动时设置 `NOVEL_DATABASE_URL`，数据库固定写入系统用户数据目录：macOS 为 `~/Library/Application Support/剧本刷`，Windows 为 `%APPDATA%/剧本刷`。从 IdeaFlash Story 升级时，会在首次启动自动迁移原用户数据。安装包、应用升级和卸载流程均不应删除该目录。

## 开发与构建

```bash
# 第一次：创建后端虚拟环境并安装常规依赖
cd backend && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd .. && npm install

# 桌面开发：Electron 会自行拉起本地 FastAPI；另一个进程运行 Vite
npm run desktop:dev

# macOS：生成当前架构的 sidecar、前端与 DMG/ZIP
npm run desktop:make:mac

# Windows PowerShell：生成 .exe sidecar、Setup.exe、.nupkg 与 RELEASES
npm run desktop:make:win
```

构建产物在 `out/`。macOS 会产生 `.dmg`（首次安装）和 `.zip`（自动更新）；Windows 会产生 `Setup.exe`、`.nupkg` 和 `RELEASES`。

两个完整打包入口均位于 `script/`：

- `script/package-macos.sh`：调用前端构建、`build-desktop-backend.sh` 和 Electron Forge。默认采用当前 macOS 架构，可通过 `NOVEL_DESKTOP_ARCH=arm64|x64` 指定。
- `script/package-windows.ps1`：在 Windows 上创建或使用 `backend/.venv`、安装 PyInstaller、构建 `novel-server.exe`，再生成 Squirrel.Windows 分发包。默认 `x64`，支持 `NOVEL_DESKTOP_ARCH=arm64`。

不要在 macOS 上交叉生成 Windows sidecar，或在 Windows 上交叉生成 macOS sidecar；PyInstaller 产物必须在对应系统和架构上原生构建。

## 自动更新

更新使用 Electron 官方 `autoUpdater` 的静态文件存储方式，Electron Forge 负责生成平台更新元数据。发布服务器只需是公开 HTTPS 的对象存储或 CDN，例如 Cloudflare R2、S3、OSS、COS。

1. 设置更新根地址并构建：

   ```bash
   NOVEL_UPDATE_BASE_URL=https://updates.example.com/script-run npm run desktop:make
   ```

2. 上传本次构建生成的更新文件，目录必须按平台和架构组织：

   ```text
   https://updates.example.com/script-run/
   ├── darwin/arm64/RELEASES.json
   ├── darwin/arm64/剧本刷-<version>-darwin-arm64.zip
   ├── darwin/x64/...
   └── win32/x64/RELEASES
   ```

3. 在 `desktop/update-config.json` 写入同一个根地址，再重新构建发布包。该文件没有密钥，可随安装包公开：

   ```json
   { "baseUrl": "https://updates.example.com/script-run" }
   ```

应用仅在生产包中检查更新；下载完成后由系统提示重启应用后安装。未配置 `baseUrl` 时自动更新完全禁用，适合本地测试和手动分发。

## 版本、数据迁移与回滚

- 每次发布同步更新根目录 `package.json` 的 `version`，禁止覆盖已有版本的更新文件。
- `backend/database.py` 的 `app_schema_migrations` 记录当前数据库基线。未来任何表/列变更必须新增顺序迁移，不能依赖删除用户表重建。
- 更新前的兼容原则是：新应用必须能够打开上一版数据库；数据迁移只允许向前追加或可逆变更。
- 若发布版本故障，应在更新源撤回该版本并发布一个更高版本的修复包；已安装用户的数据目录不回滚、不删除。

## 发布前置条件

- macOS 自动更新需要 Developer ID 签名与公证；未签名包只能手动绕过 Gatekeeper，不能作为正式更新渠道。
- Windows 应使用代码签名证书，避免 SmartScreen 警告。
- macOS 与 Windows 分别在对应操作系统构建，并分别验证首次安装、自动升级和保留旧数据库三项流程。
