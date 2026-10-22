# ideaFlash Novel

独立运行的 AI 小说写作与剧本体验工作台。仓库不依赖共享平台或内核服务。

## 本地开发

```bash
cp .env.example .env
npm install
cd backend && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd .. && npm run dev
```

也可以使用一键更新并重启脚本：

```bash
bash tmp/restart.sh
```

脚本会拉取当前分支最新代码、安装前后端依赖、停止旧进程并启动 API 与 Web。跳过拉取或依赖安装：

```bash
NOVEL_SKIP_PULL=1 NOVEL_SKIP_INSTALL=1 bash tmp/restart.sh
```

- Web：<http://127.0.0.1:5179>
- API：<http://127.0.0.1:8004/docs>

`.env` 至少配置一个 OpenAI 兼容的 LLM；本地管理员账号固定为 `ideaFlash / ideaFlash`：

```env
NOVEL_JWT_SECRET=change-this-secret
NOVEL_LLM_BASE_URL=https://api.openai.com/v1
NOVEL_LLM_API_KEY=your-api-key
NOVEL_LLM_MODEL=gpt-4o-mini
```

剧本对话可使用 `NOVEL_LLM_SCRIPT_*` 覆盖通用 LLM 配置。数据库默认写入 `backend/novel.db`，工件默认写入 `backend/data/`；可分别使用 `NOVEL_DATABASE_URL` 和 `NOVEL_DATA_DIR` 覆盖。

## 功能

- 新建小说并生成、审校、采纳章节
- 导入 `.txt`、`.md`、`.zip` 剧本并抽取人物、关系和记忆
- 副本快照、角色卡和角色临时对话
- 本地单管理员登录

## 测试

```bash
cd backend
pytest -q
```

本仓库不提交 `.env`、数据库、日志、虚拟环境和前端构建产物。
